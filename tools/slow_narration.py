"""Slow the Module I-1 narration by 10% and retime captions and declared durations.
Runs in the Pages workflow on the unzipped course folder."""
import glob, os, re, subprocess, sys
R = 0.9
os.chdir(sys.argv[1])
for f in sorted(glob.glob('assets/narration/*.mp3')):
    tmp = f + '.tmp.mp3'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f, '-filter:a', 'atempo=%s' % R, '-ar', '22050', '-ac', '1', '-b:a', '48k', tmp], check=True)
    os.replace(tmp, f)
def scale(m):
    t = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) / R
    return '%02d:%02d:%06.3f' % (t // 3600, t % 3600 // 60, t % 60)
for f in glob.glob('assets/narration/*.vtt'):
    s = open(f).read()
    open(f, 'w').write(re.sub(r'(\d\d):(\d\d):(\d\d\.\d{3})', scale, s))
def dur(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p], capture_output=True, text=True).stdout)
def fix(m):
    tag = m.group(0)
    sid = re.search(r'narration/([^"]+)\.mp3', tag).group(1)
    d = dur('assets/narration/%s.mp3' % sid)
    tag = re.sub(r'data-duration="[\d.]+"', 'data-duration="%.2f"' % d, tag)
    return re.sub(r'this screen, \d+ seconds', 'this screen, %d seconds' % round(d), tag)
h = open('index.html').read()
open('index.html', 'w').write(re.sub(r'<audio[^>]*>', fix, h))
print('narration slowed')
