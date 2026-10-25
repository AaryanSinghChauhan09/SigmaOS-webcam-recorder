    # SigmaOS-webcam-recorder

    Webcam photo / video recorder

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/omacom/monologue

    ## Design principles applied
    - **Separation of Concerns**
- **Defensive Programming**
- **Fail-Fast**
- **KISS**
- **Deterministic Testing**

    ## Usage
    Verbs: `devices, photo-plan, video-plan, effects`

    ```
    $ sigma-webcam devices v4l2.txt
Integrated Camera  ->  /dev/video0 /dev/video1
$ sigma-webcam photo-plan --device /dev/video0 --out snap.jpg --res 1280x720
fswebcam -d /dev/video0 -r 1280x720 --no-banner snap.jpg
$ sigma-webcam video-plan --device /dev/video0 --out clip.mp4 --duration 10
ffmpeg -y -f v4l2 -framerate 30 -i /dev/video0 -t 10 -pix_fmt yuv420p clip.mp4
$ sigma-webcam effects hflip grayscale
-hvf hflip,hue=s=0

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
