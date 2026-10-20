"""Time every caption cue to the moment its words are actually spoken.
Usage: python3 align_captions.py <course folder>
Speech recognition (faster-whisper) gives a time for each spoken word; the
caption text itself is never changed, only the cue start and end times."""
import difflib, glob, os, re, subprocess, sys
from faster_whisper import WhisperModel
os.chdir(sys.argv[1])
model = WhisperModel('small.en', device='cpu', compute_type='int8')

def norm(w):
    return re.sub(r"[^a-z0-9]", '', w.lower())
def ts(t):
    h, m, s = t.split(':'); return int(h) * 3600 + int(m) * 60 + float(s)
def fmt(t):
    t = max(0.0, t); return '%02d:%02d:%06.3f' % (t // 3600, t % 3600 // 60, t % 60)
def dur(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
                                capture_output=True, text=True).stdout)

for vtt in sorted(glob.glob('assets/narration/*.vtt')):
    mp3 = vtt[:-4] + '.mp3'
    blocks = open(vtt).read().strip().split('\n\n')
    head, cues = blocks[0], []
    for b in blocks[1:]:
        lines = b.split('\n')
        k = next(i for i, l in enumerate(lines) if '-->' in l)
        a, z = [x.strip().split(' ')[0] for x in lines[k].split('-->')]
        cues.append({'pre': lines[:k], 'text': lines[k + 1:], 'a': ts(a), 'z': ts(z)})
    words, owner = [], []
    for ci, c in enumerate(cues):
        for w in ' '.join(c['text']).split():
            words.append(norm(w)); owner.append(ci)
    script = ' '.join(' '.join(c['text']) for c in cues)
    segs, _ = model.transcribe(mp3, language='en', word_timestamps=True, beam_size=5,
                               initial_prompt=script[:800], condition_on_previous_text=False)
    heard = [(norm(w.word), w.start, w.end) for s in segs for w in (s.words or []) if norm(w.word)]
    sm = difflib.SequenceMatcher(None, words, [h[0] for h in heard], autojunk=False)
    st, en = [None] * len(words), [None] * len(words)
    for blk in sm.get_matching_blocks():
        for j in range(blk.size):
            st[blk.a + j], en[blk.a + j] = heard[blk.b + j][1], heard[blk.b + j][2]
    matched = sum(x is not None for x in st)
    if not words or matched < 0.6 * len(words):
        print('%s: only %d/%d words matched, kept proportional timing' % (vtt, matched, len(words)))
        continue
    total = dur(mp3)
    # fill unmatched words by interpolating between matched neighbours
    known = [i for i in range(len(words)) if st[i] is not None]
    for i in range(len(words)):
        if st[i] is None:
            lo = max([k for k in known if k < i], default=None)
            hi = min([k for k in known if k > i], default=None)
            t0 = en[lo] if lo is not None else 0.0
            t1 = st[hi] if hi is not None else total
            n0 = lo if lo is not None else -1
            n1 = hi if hi is not None else len(words)
            frac = (i - n0) / (n1 - n0)
            st[i] = t0 + (t1 - t0) * frac - 0.0
            en[i] = st[i] + (t1 - t0) / (n1 - n0)
    for ci, c in enumerate(cues):
        idx = [i for i, o in enumerate(owner) if o == ci]
        if idx:
            c['a'] = max(0.0, st[idx[0]] - 0.08)
            c['z'] = min(total, en[idx[-1]] + 0.2)
    for ci in range(len(cues) - 1):
        nxt = cues[ci + 1]['a']
        if cues[ci]['z'] > nxt or nxt - cues[ci]['z'] < 0.35:
            cues[ci]['z'] = nxt
        if cues[ci]['z'] - cues[ci]['a'] < 0.6:
            cues[ci]['z'] = min(nxt, cues[ci]['a'] + 0.6)
    out = [head]
    for c in cues:
        out.append('\n'.join(c['pre'] + ['%s --> %s' % (fmt(c['a']), fmt(c['z']))] + c['text']))
    open(vtt, 'w').write('\n\n'.join(out) + '\n')
    print('%s: %d/%d words aligned' % (vtt, matched, len(words)))
print('captions aligned')
