# Camera Setup Guide

## Overview

The plant care system uses a USB webcam (Logitech C930e) to capture photos of the plant. The camera is configured to:

1. **Open fresh for each photo** (per-capture pattern) - prevents buffer staleness
2. **Flush buffer before capturing** (10 frames) - ensures current, not stale, images
3. **Configure focus at system level** via `v4l2-ctl` - reliable and persistent

## Quick Setup (Raspberry Pi)

**Note:** The `camera-focus.service` is automatically installed when you run `install-mcp-server.sh`. This service sets focus to `focus_absolute=10` by default (close-up monitoring). If your setup is different, follow the calibration steps below.

### 1. Check Camera Connection

```bash
# List video devices
ls -la /dev/video*

# Should show: /dev/video0 (or similar)
```

### 2. Test Current Focus (Optional - if photos are blurry)

The Logitech C930e uses autofocus by default, which can produce blurry photos. Here's how to set manual focus:

```bash
# 1. List available controls
v4l2-ctl -d /dev/video0 --list-ctrls | grep focus

# You should see:
#   focus_absolute (int) : min=0 max=255 step=5 default=0 value=45 flags=inactive
#   focus_automatic_continuous (bool) : default=1 value=1

# 2. Disable continuous autofocus (this makes focus_absolute active)
v4l2-ctl -d /dev/video0 --set-ctrl focus_automatic_continuous=0

# 3. Set manual focus value (start with 60 for ~50cm distance)
v4l2-ctl -d /dev/video0 --set-ctrl focus_absolute=60

# 4. Test the photo via web UI: http://<raspberry-pi>:8000/gallery
#    Click "Take Photo" and review

# 5. Adjust focus value until sharp:
v4l2-ctl -d /dev/video0 --set-ctrl focus_absolute=40  # closer
v4l2-ctl -d /dev/video0 --set-ctrl focus_absolute=80  # farther

# Typical ranges:
#   40-60:  Close-up (20-40cm) - plant on desk
#   60-80:  Medium (50-80cm) - shelf camera
#   80-120: Far (80-120cm) - wall-mounted
```

### 3. Make Focus Settings Persistent

**Problem:** Settings may reset when camera reopens or system reboots.

**Solution:** The `camera-focus.service` is automatically installed by `install-mcp-server.sh`.

The service runs on boot and sets:
- `focus_automatic_continuous=0` (disables autofocus)
- `focus_absolute=10` (default: calibrated for close-up ~10-20cm)

**If your plant is at a different distance**, edit the service file:

```bash
# 1. Edit the service file
sudo nano /etc/systemd/system/camera-focus.service

# 2. Find this line:
#    ExecStart=/usr/bin/v4l2-ctl -d /dev/video0 --set-ctrl focus_absolute=10

# 3. Change 10 to your calibrated value (e.g., 60 for medium distance)

# 4. Save and reload
sudo systemctl daemon-reload
sudo systemctl restart camera-focus.service

# 5. Verify it's working
sudo systemctl status camera-focus.service
v4l2-ctl -d /dev/video0 --get-ctrl focus_absolute
```

## Troubleshooting

### "Permission denied" when setting focus

This can happen if:
1. **Camera is in use** - Close browser tabs with /gallery, restart MCP server
2. **Timing issue** - Camera device not fully initialized yet

**Solutions:**

```bash
# 1. Check if camera is in use
sudo lsof /dev/video0

# 2. Kill processes using camera
sudo kill <PID>

# 3. Restart MCP server
sudo systemctl restart plant-care-mcp

# 4. Try setting focus again
v4l2-ctl -d /dev/video0 --set-ctrl focus_automatic_continuous=0
v4l2-ctl -d /dev/video0 --set-ctrl focus_absolute=60
```

### Focus still blurry after setting

1. **Verify autofocus is actually disabled:**

```bash
v4l2-ctl -d /dev/video0 --get-ctrl focus_automatic_continuous
# Should return: focus_automatic_continuous: 0
```

2. **Check if focus_absolute is active:**

```bash
v4l2-ctl -d /dev/video0 --list-ctrls | grep focus_absolute
# Should NOT show "flags=inactive"
```

3. **Try a wider range of values:**

```bash
# Test from close to far
for i in 20 40 60 80 100 120; do
    echo "Testing focus=$i"
    v4l2-ctl -d /dev/video0 --set-ctrl focus_absolute=$i
    sleep 2  # Wait for focus motor
    # Now take photo via web UI and check sharpness
done
```

### Photos still look identical (stale buffer)

The per-capture pattern should fix this, but if you still see it:

1. **Increase buffer flush** in `.env`:

```bash
CAMERA_BUFFER_FLUSH_FRAMES=15  # Increase from 10
```

2. **Add more warm-up time:**

```bash
CAMERA_WARMUP_MS=300  # Increase from 150
```

3. **Verify camera is actually closing** - check logs for "Camera released" debug messages

## Configuration Reference

### Environment Variables (.env)

```bash
# Camera device (usually 0 for /dev/video0)
CAMERA_DEVICE_INDEX=0

# Image settings
CAMERA_IMAGE_WIDTH=1920
CAMERA_IMAGE_HEIGHT=1080
CAMERA_IMAGE_QUALITY=85  # JPEG quality 1-100

# Buffer flushing (clears stale frames)
CAMERA_BUFFER_FLUSH_FRAMES=10  # Read/discard 10 frames before capture

# Warm-up delay (sensor stabilization)
CAMERA_WARMUP_MS=150  # 150ms delay after opening camera
```

### v4l2-ctl Reference

```bash
# List all controls
v4l2-ctl -d /dev/video0 --list-ctrls

# Get current value
v4l2-ctl -d /dev/video0 --get-ctrl focus_automatic_continuous
v4l2-ctl -d /dev/video0 --get-ctrl focus_absolute

# Set value
v4l2-ctl -d /dev/video0 --set-ctrl focus_automatic_continuous=0
v4l2-ctl -d /dev/video0 --set-ctrl focus_absolute=60

# Other useful settings
v4l2-ctl -d /dev/video0 --set-ctrl sharpness=150        # Increase sharpness
v4l2-ctl -d /dev/video0 --set-ctrl saturation=128       # Adjust color
v4l2-ctl -d /dev/video0 --set-ctrl brightness=128       # Adjust brightness
```

## Testing

### Quick Test

```bash
# On Raspberry Pi
cd /home/mcpserver/plant-care-app/app
uv run python scripts/camera_manual_check.py

# Expected output:
# ✅ Camera available
# ✅ Photo captured successfully
# File size: ~500 KB (varies)
```

### Web UI Test

1. Navigate to `http://<raspberry-pi>:8000/gallery`
2. Click "Take Photo"
3. Verify photo is sharp and current (check timestamp)
4. Take another photo immediately - should be different (not from buffer)

## Camera Specifications

**Logitech C930e:**
- Resolution: Up to 1920x1080 @ 30fps
- Focus: Continuous autofocus (can be disabled)
- Focus Range: 0-255 (5 step increments)
- Field of View: 90°
- Connection: USB 2.0
- Linux Support: V4L2/UVC compliant

## Additional Resources

- [V4L2 Documentation](https://linuxtv.org/wiki/index.php/V4l-utils)
- [Logitech C930e Specs](https://www.logitech.com/en-us/products/webcams/c930e-business-webcam.html)
- [UVC Driver](https://www.kernel.org/doc/html/latest/admin-guide/media/uvcvideo.html)
