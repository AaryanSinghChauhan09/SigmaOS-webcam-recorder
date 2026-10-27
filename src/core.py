"""Webcam photo/video recorder planner for SigmaOS-webcam-recorder (monologue).

The engine parses v4l2 device listings, plans fswebcam/ffmpeg photo and video
captures and composes ffmpeg filter chains from named effects. Device access
and spawning are the thin execute layer -- self_test() only exercises the
pure parse/plan layer (no subprocess, no /dev access).
Principles: Separation of Concerns, Defensive Programming, Fail-Fast, KISS.
"""
import argparse, re, shlex, sys

ENGINE = {
    "name": "sigma-webcam",
    "summary": "Plan webcam photos/videos and video effect chains",
    "language": "python",
    "verbs": ["devices", "photo-plan", "video-plan", "effects"],
    "principles": ["Separation of Concerns", "Defensive Programming",
                   "Fail-Fast", "KISS", "Deterministic Testing"],
}

cli_doc = """\
$ sigma-webcam devices v4l2.txt
Integrated Camera  ->  /dev/video0 /dev/video1
$ sigma-webcam photo-plan --device /dev/video0 --out snap.jpg --res 1280x720
fswebcam -d /dev/video0 -r 1280x720 --no-banner snap.jpg
$ sigma-webcam video-plan --device /dev/video0 --out clip.mp4 --duration 10
ffmpeg -y -f v4l2 -framerate 30 -i /dev/video0 -t 10 -pix_fmt yuv420p clip.mp4
$ sigma-webcam effects hflip grayscale
-hvf hflip,hue=s=0
"""


class WebcamError(Exception):
    pass


EFFECTS = {
    "hflip": "hflip",
    "vflip": "vflip",
    "mirror": "hflip",
    "grayscale": "hue=s=0",
    "sepia": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "negate": "negate",
    "rotate90": "transpose=1",
    "rotate180": "transpose=1,transpose=1",
    "blur": "gblur=sigma=2",
    "sharpen": "unsharp=5:5:1.0:5:5:0.0",
    "denoise": "hqdn3d=4:3:6:4",
    "eq": "eq=brightness=0.06:saturation=1.15",
}
PHOTO_TOOLS = ("fswebcam", "ffmpeg")
_RES_RE = re.compile(r"^(\d+)x(\d+)$")


# --------------------------------------------------------------------------- #
#  PURE parse / plan layer
# --------------------------------------------------------------------------- #
def parse_devices(text):
    """Parse `v4l2-ctl --list-devices` output into device records."""
    devices, name, nodes = [], None, []

    def flush():
        if name is not None and nodes:
            devices.append({"name": name, "nodes": list(nodes)})

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line.strip():
            flush()
            name, nodes = None, []
            continue
        if line.startswith("/dev/"):
            if name is None:
                raise WebcamError(f"line {lineno}: device node without a header")
            nodes.append(line.strip())
            continue
        if line.endswith(":"):
            flush()
            name = line[:-1].strip()
            # strip the trailing bus-path parenthetical: "Cam (usb-00:11.2)"
            m = re.match(r"^(.*?)\s*\([^()]*\)$", name)
            if m and m.group(1).strip():
                name = m.group(1).strip()
            nodes = []
            continue
        raise WebcamError(f"line {lineno}: unparseable: {line.strip()!r}")
    flush()
    if not devices:
        raise WebcamError("no capture devices found")
    return devices


def parse_res(res):
    if not isinstance(res, str):
        raise WebcamError(f"bad resolution: {res!r}")
    m = _RES_RE.match(res.strip())
    if not m:
        raise WebcamError(f"bad resolution: {res!r} (expected WIDTHxHEIGHT)")
    w, h = int(m.group(1)), int(m.group(2))
    if not (16 <= w <= 7680 and 16 <= h <= 4320):
        raise WebcamError("resolution out of range (16..7680 x 16..4320)")
    return {"w": w, "h": h}


def _check_node(node):
    if not isinstance(node, str) or not re.match(r"^/dev/video\d+$", node):
        raise WebcamError(f"bad capture node: {node!r} (expected /dev/videoN)")
    return node


def photo_plan(node, output, res="1280x720", tool="fswebcam"):
    """Build the still-photo argv for a capture node."""
    _check_node(node)
    if not output:
        raise WebcamError("no output path")
    if tool not in PHOTO_TOOLS:
        raise WebcamError(f"unknown tool: {tool!r} (choose from {', '.join(PHOTO_TOOLS)})")
    parse_res(res)
    if tool == "fswebcam":
        return ["fswebcam", "-d", node, "-r", res, "--no-banner", output]
    return ["ffmpeg", "-y", "-f", "v4l2", "-i", node, "-frames:v", "1", output]


def video_plan(node, output, duration=10, fps=30, res=None, effects=()):
    """Build the video-capture argv for a capture node."""
    _check_node(node)
    if not output:
        raise WebcamError("no output path")
    try:
        duration = int(duration)
        fps = int(fps)
    except (TypeError, ValueError):
        raise WebcamError("duration and fps must be integers")
    if not (1 <= duration <= 3600):
        raise WebcamError("duration must be 1..3600 seconds")
    if not (1 <= fps <= 120):
        raise WebcamError("fps must be 1..120")
    if res is not None:
        parse_res(res)
    chain = effects_plan(effects)
    argv = ["ffmpeg", "-y", "-f", "v4l2", "-framerate", str(fps)]
    if res is not None:
        argv += ["-video_size", res]
    argv += ["-i", node]
    if chain:
        argv += ["-vf", chain]
    argv += ["-t", str(duration), "-pix_fmt", "yuv420p", output]
    return argv


def effects_plan(names):
    """Compose an ffmpeg filter chain from named effects."""
    if names is None:
        return None
    try:
        names = list(names)
    except TypeError:
        raise WebcamError("effects must be a list of names")
    filters = []
    for n in names:
        f = EFFECTS.get(n)
        if f is None:
            raise WebcamError(f"unknown effect {n!r} "
                              f"(choose from {', '.join(sorted(EFFECTS))})")
        if f not in filters:       # de-duplicate while keeping order
            filters.append(f)
    return ",".join(filters) if filters else None


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    sub = p.add_subparsers(dest="cmd", required=True)
    dv = sub.add_parser("devices", help="parse a v4l2 device listing")
    dv.add_argument("file")
    ph = sub.add_parser("photo-plan", help="build a still-photo invocation")
    ph.add_argument("--device", required=True)
    ph.add_argument("--out", required=True)
    ph.add_argument("--res", default="1280x720")
    ph.add_argument("--tool", default="fswebcam", choices=list(PHOTO_TOOLS))
    vd = sub.add_parser("video-plan", help="build a video-capture invocation")
    vd.add_argument("--device", required=True)
    vd.add_argument("--out", required=True)
    vd.add_argument("--duration", type=int, default=10)
    vd.add_argument("--fps", type=int, default=30)
    vd.add_argument("--res", default=None)
    vd.add_argument("--effect", action="append", default=[],
                    help="named effect (repeatable)")
    ef = sub.add_parser("effects", help="compose an ffmpeg filter chain")
    ef.add_argument("name", nargs="+", choices=sorted(EFFECTS))
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "devices":
            for d in parse_devices(_read(args.file)):
                print(f'{d["name"]}  ->  {" ".join(d["nodes"])}')
        elif args.cmd == "photo-plan":
            plan = photo_plan(args.device, args.out, args.res, args.tool)
            print(" ".join(shlex.quote(a) for a in plan))
        elif args.cmd == "video-plan":
            plan = video_plan(args.device, args.out, args.duration, args.fps,
                              args.res, args.effect)
            print(" ".join(shlex.quote(a) for a in plan))
        elif args.cmd == "effects":
            chain = effects_plan(args.name)
            print(f"-hvf {chain}" if chain else "(no effects)")
        return 0
    except WebcamError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


# --------------------------------------------------------------------------- #
#  Tests (pure parse/plan layer only)
# --------------------------------------------------------------------------- #
SAMPLE_V4L2 = """Integrated Camera (usb-0000:00:14.0-1):
	/dev/video0
	/dev/video1

HP TrueVision HD (usb-0000:00:14.0-2):
	/dev/video2
"""


def self_test() -> None:
    devs = parse_devices(SAMPLE_V4L2)
    assert len(devs) == 2, devs
    assert devs[0]["name"] == "Integrated Camera"
    assert devs[0]["nodes"] == ["/dev/video0", "/dev/video1"]
    assert devs[1] == {"name": "HP TrueVision HD", "nodes": ["/dev/video2"]}
    # header flushed at EOF without trailing blank line
    assert parse_devices("Cam (x):\n\t/dev/video0\n")[0]["nodes"] == ["/dev/video0"]
    for bad in ("", "just text\n", "\t/dev/video0\n"):
        try:
            parse_devices(bad)
        except WebcamError:
            pass
        else:
            raise AssertionError(f"bad device listing not rejected: {bad!r}")

    assert parse_res("1920x1080") == {"w": 1920, "h": 1080}
    for bad in ("1920", "0x1080", "abc", "1920x", None):
        try:
            parse_res(bad)
        except WebcamError:
            pass
        else:
            raise AssertionError(f"bad resolution not rejected: {bad!r}")

    plan = photo_plan("/dev/video0", "snap.jpg", "1280x720")
    assert plan == ["fswebcam", "-d", "/dev/video0", "-r", "1280x720",
                    "--no-banner", "snap.jpg"], plan
    plan = photo_plan("/dev/video0", "snap.png", tool="ffmpeg")
    assert plan == ["ffmpeg", "-y", "-f", "v4l2", "-i", "/dev/video0",
                    "-frames:v", "1", "snap.png"], plan
    for bad in (("/dev/video", "x.jpg", "1280x720", "fswebcam"),
                ("/dev/video0", "", "1280x720", "fswebcam"),
                ("/dev/video0", "x.jpg", "huge", "fswebcam"),
                ("/dev/video0", "x.jpg", "1280x720", "mplayer")):
        try:
            photo_plan(bad[0], bad[1], bad[2], bad[3])
        except WebcamError:
            pass
        else:
            raise AssertionError(f"bad photo plan not rejected: {bad!r}")

    plan = video_plan("/dev/video0", "clip.mp4", duration=10, fps=30,
                      res="1280x720", effects=["hflip", "grayscale"])
    assert plan[0] == "ffmpeg" and "-framerate" in plan
    assert plan[plan.index("-t") + 1] == "10"
    assert plan[plan.index("-vf") + 1] == "hflip,hue=s=0"
    assert plan[plan.index("-video_size") + 1] == "1280x720"
    assert plan[-1] == "clip.mp4"
    plain = video_plan("/dev/video1", "clip.mkv")
    assert "-vf" not in plain and plain[plain.index("-t") + 1] == "10"
    for bad in (("/dev/video0", "x.mp4", 0, 30, None, ()),
                ("/dev/video0", "x.mp4", 10, 0, None, ()),
                ("/dev/video0", "x.mp4", 10, 30, "bad", ()),
                ("/dev/video0", "x.mp4", 10, 30, None, ("spin",))):
        try:
            video_plan(*bad)
        except WebcamError:
            pass
        else:
            raise AssertionError(f"bad video plan not rejected: {bad!r}")

    assert effects_plan(["hflip", "vflip"]) == "hflip,vflip"
    assert effects_plan(["hflip", "mirror"]) == "hflip"        # de-duplicated
    assert effects_plan([]) is None and effects_plan(None) is None
    try:
        effects_plan(["hflip", "warp"])
    except WebcamError as e:
        assert "unknown effect" in str(e)
    else:
        raise AssertionError("unknown effect not rejected")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
