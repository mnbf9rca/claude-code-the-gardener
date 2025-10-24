# installing on rpi

os: `raspberry pi os lite (64-bit)`

```shell
sudo apt-get update && DEBIAN_FRONTEND=noninteractive sudo apt-get upgrade -y --no-install-recommends
```


install uv 

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

install git

```shell
DEBIAN_FRONTEND=noninteractive sudo apt-get install -y --no-install-recommends git libopencv-dev v4l-utils python3-numpy python3-pip python3-matplotlib acl
```

clone repo and install dependencies

```shell
cd ~
git clone https://github.com/mnbf9rca/claude-code-the-gardener.git
cd claude-code-the-gardener/app
uv sync --no-group dev
```

add user to video group for camera access

```shell
sudo usermod -aG video $USER
newgrp video # to apply group change without logout
```

test camera

```shell
uv run python scripts/camera_manual_check.py
```

you should get an output like this:

```shell
rob@raspberrypi:~/claude-code-the-gardener/app $ uv run python scripts/camera_manual_check.py
2025-10-19 21:34:20 - root - INFO - Loaded 1 photos from disk into history
2025-10-19 21:34:20 - tools.light - WARNING - Light tool configuration errors:
  - HOME_ASSISTANT_TOKEN is not set or empty
2025-10-19 21:34:20 - tools.light - WARNING - Light tools will run in fallback mode. Set environment variables to enable Home Assistant integration.
Starting camera hardware diagnostic...
Make sure your USB camera is connected.
Current device index: 0
If camera not found, try editing CAMERA_DEVICE_INDEX in this file.

============================================================
CAMERA HARDWARE DIAGNOSTIC CHECK
============================================================

1. Checking camera status...
2025-10-19 21:34:22 - root - INFO - Camera initialized successfully on device 0
{
  "camera_enabled": true,
  "camera_available": true,
  "device_index": 0,
  "save_path": "test_photos",
  "resolution": "1920x1080",
  "image_quality": 85,
  "photos_captured": 1,
  "error": null
}

2. Testing photo capture...
2025-10-19 21:34:23 - root - INFO - Photo captured: test_photos/plant_20251019_203423_405.jpg
   Success: True
   HTTP URL: http://localhost:8000/photos/plant_20251019_203423_405.jpg
   Local path: test_photos/plant_20251019_203423_405.jpg

✅ Camera capture successful!
   File size: 134.8 KB

3. Testing recent photos retrieval...
   Found 2 recent photos
   1. Time: 2025-10-19T20:32:51
   2. Time: 2025-10-19T20:34:23

============================================================
DIAGNOSTIC CHECK COMPLETE
============================================================
2025-10-19 21:34:23 - root - INFO - Camera released
```

You can check for the file with e.g. `ls test_photos/plant_20251019_203423_405.jpg` (in this case), or copy it locally with e.g. `scp rob@192.168.17.145:/home/rob/claude-code-the-gardener/app/test_photos/plant_20251019_203423_405.jpg ~/Downloads/` (substitute in your own username and IP address).

Then set your .env file. Copy the example and edit:

```shell
cp .env.example .env
nano .env
```

Set at least the following variables:

```shell
MCP_PUBLIC_HOST=your-ip-or-hostname-here
HOME_ASSISTANT_URL=http://your-home-assistant.local:8123
HOME_ASSISTANT_TOKEN=your-long-lived-access-token
LIGHT_ENTITY_ID=your-smart-plug-entity-id
```

Then run the server to test it:

```shell
uv run python run_http.py
```

you can then connect it to claude code running, say, on your laptop:

```shell
# make a temp dir so that we can have a clean claude config
mkdir temp
cd temp
claude mcp add --transport http plant-tools http://192.168.17.145:8000/mcp
```

It should respond with something like this:

```shell
Added HTTP MCP server plant-tools with URL: http://192.168.17.145:8000/mcp to local config
File modified: /Users/rob/.claude.json [project: /Users/rob/Downloads/temp]
```

we can then check the server status with `claude mcp list` and get:

```shell
Checking MCP server health...

plant-tools: http://192.168.17.145:8000/mcp (HTTP) - ✓ Connected
```

If we then launch claude code with the plant tools MCP server connected and ask it, we can see it is registered:

```shell
╭─── Claude Code v2.0.22 ──────────────────────────────────────────────────────────────╮
│                               │ Tips for getting started                             │
│       Welcome back Rob!       │ Ask Claude to create a new app or clone a repository │
│                               │ ──────────────────────────────────────────────────── │
│            ▐▛███▜▌            │ Recent activity                                      │
│           ▝▜█████▛▘           │ No recent activity                                   │
│             ▘▘ ▝▝             │                                                      │
│                               │                                                      │
│    Sonnet 4.5 · Claude Max    │                                                      │
│   /Users/rob/Downloads/temp   │                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────╯

> tell me about your tools

⏺ I have access to several categories of tools:

  File Operations

  - Read - Read files from the filesystem (supports code, images, PDFs, Jupyter notebooks)
  - Write - Create new files or overwrite existing ones
  - Edit - Make precise string replacements in existing files
  - Glob - Find files using patterns like **/*.js
  - Grep - Search file contents using regex (powered by ripgrep)

  Code Execution

  - Bash - Execute shell commands (git, npm, docker, etc.)
  - BashOutput - Monitor output from background bash processes
  - KillShell - Terminate running background shells
  - NotebookEdit - Edit Jupyter notebook cells

  Task Management

  - TodoWrite - Create and track task lists for complex work
  - Task - Launch specialized agents for complex tasks:
    - general-purpose - Multi-step research and coding
    - Explore - Fast codebase exploration and search
    - statusline-setup - Configure status line
    - output-style-setup - Create output styles

  Web Access

  - WebFetch - Fetch and analyze web content
  - WebSearch - Search the web for current information

  User Interaction

  - AskUserQuestion - Ask multiple-choice questions during execution
  - ExitPlanMode - Present implementation plans for approval

  MCP Resources

  - ListMcpResourcesTool - List resources from MCP servers
  - ReadMcpResourceTool - Read specific MCP resources

  Plant Care Tools (MCP)

  I also have access to a complete plant monitoring system:
  - Moisture sensing and history
  - Automated watering (10-100ml, 500ml/24h limit)
  - Grow light control (30-120 min sessions)
  - Camera for plant photos
  - Thought and action logging for reasoning
  - Status tracking and history

  Is there a specific tool category you'd like to know more about?
```

and if we ask it the time:

```shell
> what's the exact time

╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Tool use                                                                                                                                                                                                │
│                                                                                                                                                                                                         │
│   plant-tools - get_current_time() (MCP)                                                                                                                                                                │
│   Get the current UTC time.                                                                                                                                                                             │
│   Use this to understand the current date and time for temporal reasoning.                                                                                                                              │
│                                                                                                                                                                                                         │
│ Do you want to proceed?                                                                                                                                                                                 │
│ ❯ 1. Yes                                                                                                                                                                                                │
│   2. Yes, and don't ask again for plant-tools - get_current_time commands in /Users/rob/Downloads/temp                                                                                                  │
│   3. No, and tell Claude what to do differently (esc)                                                                                                                                                   │
│                                                                                                                                                                                                         │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

we can see all of this in the streamed log output of the rpi server:

```shell
rob@raspberrypi:~/claude-code-the-gardener/app $  uv run python run_http.py
2025-10-19 22:04:00 - root - INFO - Loaded 0 photos from disk into history
2025-10-19 22:04:01 - __main__ - INFO - ============================================================
2025-10-19 22:04:01 - __main__ - INFO - 🌱 Plant Care MCP Server - HTTP Mode
2025-10-19 22:04:01 - __main__ - INFO - ============================================================
2025-10-19 22:04:01 - __main__ - INFO - Server starting on http://0.0.0.0:8000
2025-10-19 22:04:01 - __main__ - INFO - MCP endpoint: http://0.0.0.0:8000/mcp
2025-10-19 22:04:01 - __main__ - INFO - Photos endpoint: http://0.0.0.0:8000/photos/
2025-10-19 22:04:01 - __main__ - INFO - Press Ctrl+C to stop
2025-10-19 22:04:01 - __main__ - INFO - ============================================================
2025-10-19 22:04:01 - __main__ - INFO - Static files mounted: /home/rob/claude-code-the-gardener/app/photos
INFO:     Started server process Ä12391Å
INFO:     Waiting for application startup.
2025-10-19 22:04:01 - mcp.server.streamable_http_manager - INFO - StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
2025-10-19 22:06:49 - mcp.server.streamable_http_manager - INFO - Created new transport with session ID: 4e00986c6fe54f378ad1ab76125b98b2
INFO:     192.168.17.108:55850 - "POST /mcp HTTP/1.1" 200 OK
INFO:     192.168.17.108:55856 - "POST /mcp HTTP/1.1" 202 Accepted
INFO:     192.168.17.108:55850 - "GET /mcp HTTP/1.1" 200 OK
2025-10-19 22:09:02 - mcp.server.streamable_http_manager - INFO - Created new transport with session ID: 9e24f2a2161043f3931930d5a72ff521
INFO:     192.168.17.108:55933 - "POST /mcp HTTP/1.1" 200 OK
INFO:     192.168.17.108:55934 - "POST /mcp HTTP/1.1" 202 Accepted
INFO:     192.168.17.108:55933 - "GET /mcp HTTP/1.1" 200 OK
INFO:     192.168.17.108:55935 - "POST /mcp HTTP/1.1" 200 OK
INFO:     192.168.17.108:55936 - "POST /mcp HTTP/1.1" 200 OK
INFO:     192.168.17.108:55937 - "POST /mcp HTTP/1.1" 200 OK
2025-10-19 22:09:02 - mcp.server.lowlevel.server - INFO - Processing request of type ListToolsRequest
2025-10-19 22:09:02 - mcp.server.lowlevel.server - INFO - Processing request of type ListPromptsRequest
2025-10-19 22:09:02 - mcp.server.lowlevel.server - INFO - Processing request of type ListResourcesRequest
INFO:     192.168.17.108:56016 - "POST /mcp HTTP/1.1" 200 OK
2025-10-19 22:10:51 - mcp.server.lowlevel.server - INFO - Processing request of type CallToolRequest
```

For more detailed logging, adjust the `LOG_LEVEL` environment variable in your `.env` file.

ok next we need to install it as a service. We'll do that later...