#[derive(Debug, Clone)]
pub struct CameraDevice {
    pub device_node: String,
    pub max_fps: u8,
}

pub struct WebcamManager;
impl WebcamManager {
    pub fn is_valid_camera(dev: &CameraDevice) -> bool {
        dev.device_node.starts_with("/dev/video") && dev.max_fps >= 24
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_webcam_validation() {
        let cam = CameraDevice { device_node: "/dev/video0".into(), max_fps: 30 };
        assert!(WebcamManager::is_valid_camera(&cam));
    }
}
