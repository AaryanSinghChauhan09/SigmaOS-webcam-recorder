.PHONY: build test install clean
build:
	python3 -m compileall -q src
test:
	python3 -m unittest discover -s tests -v
install:
	install -Dm755 bin/sigma-webcam-recorder $(DESTDIR)/usr/bin/sigma-webcam-recorder
clean:
	rm -rf src/__pycache__ tests/__pycache__
