//! Codec management for media formats
//! Follows: Interface Segregation, Plugin Model

use std::collections::HashMap;

/// Codec type
#[derive(Debug, Clone, PartialEq)]
pub enum CodecType {
    Video,
    Audio,
    Image,
}

/// Codec specification
pub struct Codec {
    pub name: String,
    pub codec_type: CodecType,
    pub extensions: Vec<String>,
}

impl Codec {
    pub fn new(name: String, codec_type: CodecType) -> Self {
        Codec {
            name,
            codec_type,
            extensions: Vec::new(),
        }
    }

    pub fn add_extension(&mut self, ext: String) {
        self.extensions.push(ext);
    }
}

/// Codec registry
pub struct CodecRegistry {
    codecs: HashMap<String, Codec>,
}

impl CodecRegistry {
    pub fn new() -> Self {
        CodecRegistry {
            codecs: HashMap::new(),
        }
    }

    pub fn register(&mut self, codec: Codec) {
        let name = codec.name.clone();
        self.codecs.insert(name, codec);
    }

    pub fn find_by_extension(&self, ext: &str) -> Option<&Codec> {
        self.codecs.values()
            .find(|codec| codec.extensions.iter().any(|e| e.to_lowercase() == ext.to_lowercase()))
    }
}

impl Default for CodecRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_codec_registry() {
        let mut registry = CodecRegistry::new();
        let codec = Codec::new("test".to_string(), CodecType::Video);
        registry.register(codec);
        assert!(registry.codecs.contains_key("test"));
    }
}
