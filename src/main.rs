mod config;
mod error;
mod service;
mod media;
mod codec;

use config::Config;
use service::Service;
use media::MediaPlayer;
use codec::{CodecRegistry, Codec, CodecType};
use std::path::PathBuf;
use anyhow::Result;

fn main() -> Result<()> {
    env_logger::init();
    
    let config = Config::default();
    let mut service = Service::new(config);
    
    service.start()?;
    println!("Service started successfully");
    
    // Demonstrate media player
    let mut player = MediaPlayer::new();
    println!("Media player initialized");
    
    // Demonstrate codec registry
    let mut registry = CodecRegistry::new();
    let codec = Codec::new("h264".to_string(), CodecType::Video);
    registry.register(codec);
    println!("Codec registry initialized");
    
    service.stop()?;
    println!("Service stopped successfully");
    
    Ok(())
}
