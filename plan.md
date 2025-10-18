# A simple experiment to see if Claude Code can keep a plant alive

Claude will be running on a vm. It will be triggered to run once every 10 minutes by a cron job. Its prompt will instruct it to keep the plant alive by making use of its tools to see the past plan, read the status of the environment, thinking about next steps, writing that plan to a "plan tool" (MCP), and then calling the services to make a change (or do nothing if not needed).

Claude will have access to tehse tools as MCP servers over http:

- a "thinking" tool, which stores plan items - basically a key value store where the key is an index, and the value is a json object containing a "timestamp" and "thought" keys. This allows claude to maintain a log of its thoughts and actions over time.
- a "plant status and next steps" tool, which claude must write to before making any tool calls. If it has not written to this tool, no other tool calls will be executed. This is to ensure that claude is always thinking about the plant status and next steps before taking any action.
- a "moisture sensor" tool, which reads the raw value from a capacitive soil moisture sensor connected to an esp32.
- a "water pump" tool which can dispense a specific amount (10-100ml) of water when called. There is a limit of 500ml per rolling 24 hour period.
- a camera tool which can take a photo of the plant and return the image URL
- a "light" tool which can turn on/off a grow light for a specified duration (max 2 hours at a time, min 30 minutes off between activations)
- a "web search" tool which can be used to look up information about plant care if needed


The HTTP based services will be running in a FastAPI app on a raspberry pi. The camera will be connected via USB.  The ESP32 will be connected to the moisture sensor, water pump, and light. The Raspberry PI will communicate with the ESP32 with over HTTP to get sensor readings and trigger actions.

The ESP32 will be fairly simple. It will have endpoints to read the moisture sensor, activate the water pump for a specified amount of time (seconds). The ESP32 will handle the low-level control of the hardware components. All the logic like:

- tracking water usage limits
- ensuring the light is only on for the allowed duration
- converting a ml amount to pump activation time
- taking and storing photos from the USB camera
- storing and retrieving thoughts and plans

will be handled by the FastAPI app.

The ESP32 will have a safety mechanism to limit pump activation time to prevent a flood in case of any bugs in the FastAPI app.

The peristaltic pump is connected to a relay controlled by the ESP32 GPIO pins. The moisture sensor is connected to an analog input pin.

The grow light will be connected to a Meross smart plug, which can be controlled via MQTT to Home Assistant from the FastAPI app.

## hardware

ESP32 components:

- M5 cores3se: https://docs.m5stack.com/en/core/M5CoreS3%20SE
- relay: https://thepihut.com/products/2-channel-isolated-relay-breakout-5v
- pump: https://thepihut.com/products/peristaltic-liquid-pump-with-silicone-tubing-5v-to-6v-dc-power
- moisture sensor: https://thepihut.com/products/capacitive-soil-moisture-sensor

FastAPI app components:

- Raspberry Pi 4 or 5
- webcam: https://www.logitech.com/en-gb/products/webcams/c930e-business-webcam.html
- Meross smart plug: https://www.amazon.co.uk/dp/B0CNVHBCR3 
- Grow Light: https://grow-gang.com/products/pianta-grow-light

3 Power Supplies, one for the ESP32 and sensors, one for the pump, one for the Raspberry Pi.