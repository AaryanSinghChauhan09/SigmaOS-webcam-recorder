//! SigmaOS-webcam-recorder — webcam capture manager
//! (Omarchy `monologue` parity).
//!
//! Camera enumeration model, format/resolution selection, recording
//! state machine, segment rotation, and output naming. V4L2 capture
//! itself is delegated to the driver/media subsystem.

/// Supported pixel formats (V4L2 fourcc names).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PixelFormat {
    Yuyv,
    Mjpeg,
    Nv12,
    Rgb24,
}

impl PixelFormat {
    pub fn fourcc(self) -> &'static str {
        match self {
            Self::Yuyv => "YUYV",
            Self::Mjpeg => "MJPG",
            Self::Nv12 => "NV12",
            Self::Rgb24 => "RGB3",
        }
    }
}

/// A resolution/fps candidate from VIDIOC_ENUM_FMT/FRAMESIZE enumeration.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VideoFormat {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    pub format: PixelFormat,
}

/// A detected camera.
#[derive(Debug, Clone)]
pub struct CameraDevice {
    pub device_node: String,
    pub name: String,
    pub formats: Vec<VideoFormat>,
}

impl CameraDevice {
    pub fn new(device_node: &str, name: &str) -> Self {
        Self {
            device_node: device_node.into(),
            name: name.into(),
            formats: Vec::new(),
        }
    }

    /// Best format: prefer highest resolution at >= requested fps,
    /// preferring uncompressed formats over MJPEG.
    pub fn best_format(&self, min_fps: u32) -> Option<VideoFormat> {
        let fmt_rank = |f: PixelFormat| match f {
            PixelFormat::Yuyv => 0,
            PixelFormat::Nv12 => 1,
            PixelFormat::Rgb24 => 2,
            PixelFormat::Mjpeg => 3,
        };
        self.formats
            .iter()
            .filter(|f| f.fps >= min_fps)
            .min_by_key(|f| (fmt_rank(f.format), std::cmp::Reverse(f.width * f.height)))
            .copied()
    }
}

/// Recording lifecycle states.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RecordState {
    Idle,
    Recording { started_unix: i64 },
    Paused { started_unix: i64 },
}

/// Output file name: `webcam-YYYYMMDD-HHMMSS.mkv`.
pub fn output_filename(unix_secs: i64) -> String {
    let days = unix_secs.div_euclid(86_400);
    let secs = unix_secs.rem_euclid(86_400);
    let (y, m, d) = civil_from_days(days);
    format!(
        "webcam-{:04}{:02}{:02}-{:02}{:02}{:02}.mkv",
        y, m, d, secs / 3600, (secs % 3600) / 60, secs % 60
    )
}

fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (if m <= 2 { y + 1 } else { y }, m as u32, d as u32)
}

#[derive(Debug)]
pub struct WebcamRecorder {
    camera: Option<CameraDevice>,
    format: Option<VideoFormat>,
    state: RecordState,
    segment_secs: u64,
}

impl WebcamRecorder {
    pub fn new() -> Self {
        Self {
            camera: None,
            format: None,
            state: RecordState::Idle,
            segment_secs: 300,
        }
    }

    pub fn attach_camera(&mut self, cam: CameraDevice) {
        self.camera = Some(cam);
        self.format = None;
    }

    pub fn select_format(&mut self, min_fps: u32) -> Option<VideoFormat> {
        let f = self.camera.as_ref()?.best_format(min_fps);
        self.format = f;
        f
    }

    pub fn start(&mut self, unix_secs: i64) -> bool {
        if self.camera.is_none() || self.format.is_none() {
            return false;
        }
        if matches!(self.state, RecordState::Recording { .. }) {
            return false; // already recording
        }
        self.state = RecordState::Recording { started_unix: unix_secs };
        true
    }

    pub fn pause(&mut self) -> bool {
        match self.state {
            RecordState::Recording { started_unix } => {
                self.state = RecordState::Paused { started_unix };
                true
            }
            _ => false,
        }
    }

    pub fn resume(&mut self, unix_secs: i64) -> bool {
        match self.state {
            RecordState::Paused { .. } => {
                self.state = RecordState::Recording { started_unix: unix_secs };
                true
            }
            _ => false,
        }
    }

    pub fn stop(&mut self) {
        self.state = RecordState::Idle;
    }

    /// Elapsed recording seconds; 0 when idle.
    pub fn elapsed(&self, now_unix: i64) -> u64 {
        match self.state {
            RecordState::Recording { started_unix } => (now_unix - started_unix).max(0) as u64,
            RecordState::Paused { started_unix } => {
                // paused duration counted up to pause; approximate with start
                (now_unix - started_unix).max(0) as u64
            }
            RecordState::Idle => 0,
        }
    }

    /// Whether a segment rotation is due.
    pub fn segment_due(&self, now_unix: i64) -> bool {
        self.elapsed(now_unix) >= self.segment_secs
    }

    pub fn set_segment_secs(&mut self, secs: u64) {
        self.segment_secs = secs.max(1);
    }

    pub fn state(&self) -> RecordState {
        self.state
    }

    /// Legacy validation helper.
    pub fn is_valid_camera(dev: &CameraDevice) -> bool {
        dev.device_node.starts_with("/dev/video")
    }
}

impl Default for WebcamRecorder {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cam() -> CameraDevice {
        let mut c = CameraDevice::new("/dev/video0", "HD Webcam");
        c.formats = vec![
            VideoFormat { width: 640, height: 480, fps: 30, format: PixelFormat::Mjpeg },
            VideoFormat { width: 1280, height: 720, fps: 30, format: PixelFormat::Yuyv },
            VideoFormat { width: 1920, height: 1080, fps: 15, format: PixelFormat::Yuyv },
        ];
        c
    }

    #[test]
    fn test_webcam_validation() {
        let c = CameraDevice { device_node: "/dev/video0".into(), name: String::new(), formats: vec![] };
        assert!(WebcamRecorder::is_valid_camera(&c));
        let bad = CameraDevice { device_node: "/dev/sda".into(), name: String::new(), formats: vec![] };
        assert!(!WebcamRecorder::is_valid_camera(&bad));
    }

    #[test]
    fn best_format_prefers_uncompressed_hd() {
        let c = cam();
        // min 24fps: 1080p@15 excluded, 720p YUYV beats 640 MJPEG
        let f = c.best_format(24).unwrap();
        assert_eq!((f.width, f.height), (1280, 720));
        assert_eq!(f.format, PixelFormat::Yuyv);
    }

    #[test]
    fn record_state_machine() {
        let mut r = WebcamRecorder::new();
        assert!(!r.start(0)); // no camera
        r.attach_camera(cam());
        assert!(r.select_format(24).is_some());
        assert!(r.start(1000));
        assert!(!r.start(1001)); // already recording
        assert_eq!(r.elapsed(1030), 30);
        assert!(r.pause());
        assert!(!r.pause());
        assert!(r.resume(2000));
        assert_eq!(r.elapsed(2005), 5);
        r.stop();
        assert_eq!(r.state(), RecordState::Idle);
    }

    #[test]
    fn filename_and_segment() {
        let name = output_filename(1_704_113_696);
        assert!(name.starts_with("webcam-20240101-"));
        assert!(name.ends_with(".mkv"));
        let mut r = WebcamRecorder::new();
        r.set_segment_secs(10);
        assert!(!r.segment_due(0));
    }
}
