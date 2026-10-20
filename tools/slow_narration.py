"""Slow the Module I-1 narration by 10% and make the voice clearer.
Usage: python3 improve_narration.py <course folder>
Works on the original-speed files: time-domain stretch (no echo), voice EQ,
a gentle gate to keep pauses clean, and a peak limiter. 44.1 kHz 128 kbps."""
import glob, os, re, subprocess, sys
R = 0.9
os.chdir(sys.argv[1])
CHAIN = ','.join([
    'aresample=44100:resampler=soxr',
    'atempo=%s' % R,                      # time-domain stretch: no added echo
    'highpass=f=80',
    'equalizer=f=250:t=q:w=1.0:g=-2',     # less boom
    'equalizer=f=3000:t=q:w=1.5:g=2',     # more presence
    'agate=threshold=0.02:ratio=2:range=0.3:attack=2:knee=3:release=60',  # quieter tails between words
    'alimiter=limit=0.89:level=false',
])
for f in sorted(glob.glob('assets/narration/*.mp3')):
    tmp = f + '.tmp.mp3'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f, '-af', CHAIN, '-ar', '44100', '-ac', '1',
                    '-c:a', 'libmp3lame', '-b:a', '128k', tmp], check=True)
    os.replace(tmp, f)
# provisional caption timing: scale to the new speed (align_captions.py refines it)
def scale(m):
    t = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) / R
    return '%02d:%02d:%06.3f' % (t // 3600, t % 3600 // 60, t % 60)
for f in glob.glob('assets/narration/*.vtt'):
    s = open(f).read()
    open(f, 'w').write(re.sub(r'(\d\d):(\d\d):(\d\d\.\d{3})', scale, s))
def dur(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
                                capture_output=True, text=True).stdout)
def fix(m):
    tag = m.group(0)
    sid = re.search(r'narration/([^"]+)\.mp3', tag).group(1)
    d = dur('assets/narration/%s.mp3' % sid)
    tag = re.sub(r'data-duration="[\d.]+"', 'data-duration="%.2f"' % d, tag)
    return re.sub(r'this screen, \d+ seconds', 'this screen, %d seconds' % round(d), tag)
h = open('index.html').read()
open('index.html', 'w').write(re.sub(r'<audio[^>]*>', fix, h))
print('narration slowed and clarified')
