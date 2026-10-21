"""Time every caption cue to the moment its words are actually spoken.
Usage: python3 align_captions.py <course folder>
Speech recognition (faster-whisper) gives a time for each spoken word; the
caption text itself is never changed, only the cue start and end times."""
import difflib, glob, os, re, subprocess, sys
import numpy as np
from faster_whisper import WhisperModel
os.chdir(sys.argv[1])
model = WhisperModel('small.en', device='cpu', compute_type='int8')

def norm(w):
    return re.sub(r"[^a-z0-9]", '', w.lower())
def ts(t):
    h, m, s = t.split(':'); return int(h) * 3600 + int(m) * 60 + float(s)
def fmt(t):
    t = max(0.0, t); return '%02d:%02d:%06.3f' % (t // 3600, t % 3600 // 60, t % 60)
def load(p):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-f', 'f32le', '-ac', '1', '-ar', '16000', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()
def dur(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
                                capture_output=True, text=True).stdout)

def hear(audio, **opts):
    segs, _ = model.transcribe(audio, language='en', word_timestamps=True, beam_size=5, **opts)
    return [(norm(w.word), w.start, w.end) for s in segs for w in (s.words or []) if norm(w.word)]
def match(words, heard):
    sm = difflib.SequenceMatcher(None, words, [h[0] for h in heard], autojunk=False)
    st, en = [None] * len(words), [None] * len(words)
    for blk in sm.get_matching_blocks():
        for j in range(blk.size):
            st[blk.a + j], en[blk.a + j] = heard[blk.b + j][1], heard[blk.b + j][2]
    return st, en

for vtt in sorted(glob.glob('assets/narration/*.vtt')):
    mp3 = vtt[:-4] + '.mp3'
    blocks = open(vtt).read().strip().split('\n\n')
    head, cues = blocks[0], []
    for b in blocks[1:]:
        lines = b.split('\n')
        k = next(i for i, l in enumerate(lines) if '-->' in l)
        a, z = [x.strip().split(' ')[0] for x in lines[k].split('-->')]
        cues.append({'pre': lines[:k], 'text': lines[k + 1:], 'a': ts(a), 'z': ts(z)})
    # one caption per line of text, so every caption reads as a single line
    cues = [{'pre': [], 'text': [ln.strip()], 'a': c['a'], 'z': c['z']} for c in cues for ln in c['text'] if ln.strip()]
    words, owner, raw = [], [], []
    for ci, c in enumerate(cues):
        for w in ' '.join(c['text']).split():
            words.append(norm(w)); owner.append(ci); raw.append(w)
    script = ' '.join(' '.join(c['text']) for c in cues)
    audio = load(mp3)
    total = len(audio) / 16000.0
    st, en = [None] * len(words), [None] * len(words)
    tries = [dict(initial_prompt=script[:800], condition_on_previous_text=False),
             dict(vad_filter=True, condition_on_previous_text=False),
             dict(initial_prompt=script[:400], vad_filter=True, chunk_length=15)]
    best = -1
    for opts in tries:
        s1, e1 = match(words, hear(audio, **opts))
        n = sum(x is not None for x in s1)
        if n > best:
            best, st, en = n, s1, e1
        if n >= 0.97 * len(words):
            break
    # second pass: listen again to any stretch of words that was missed
    i = 0
    while i < len(words):
        if st[i] is not None:
            i += 1; continue
        j = i
        while j < len(words) and st[j] is None:
            j += 1
        if j - i >= 3:
            t0 = max(0.0, (en[i - 1] if i > 0 else 0.0) - 0.3)
            t1 = min(total, (st[j] if j < len(words) else total) + 0.3)
            if t1 - t0 > 0.5:
                clip = audio[int(t0 * 16000):int(t1 * 16000)]
                s2, e2 = match(words[i:j], hear(clip, initial_prompt=' '.join(raw[i:j]), condition_on_previous_text=False))
                for k in range(j - i):
                    if s2[k] is not None:
                        st[i + k], en[i + k] = s2[k] + t0, e2[k] + t0
        i = j
    matched = sum(x is not None for x in st)
    if not words or matched < 0.6 * len(words):
        print('%s: only %d/%d words matched, kept proportional timing' % (vtt, matched, len(words)))
        st = None
    if st is None:
        # no reliable recognition: spread the words evenly over the narration
        st = [None] * len(words); en = [None] * len(words)
        st[0], en[0] = cues[0]['a'], cues[0]['a'] + 0.3
        st[-1], en[-1] = cues[-1]['z'] - 0.3, cues[-1]['z']
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
    for n, c in enumerate(cues, 1):
        out.append('\n'.join([str(n), '%s --> %s' % (fmt(c['a']), fmt(c['z']))] + c['text']))
    open(vtt, 'w').write('\n\n'.join(out) + '\n')
    print('%s: %d/%d words aligned' % (vtt, matched, len(words)))
# show each caption on one line across the player instead of a narrow column
css = open('assets/course.css').read()
open('assets/course.css', 'w').write(css.replace('max-width: 46ch; text-wrap: pretty;', 'max-width: none;'))
print('captions aligned')
