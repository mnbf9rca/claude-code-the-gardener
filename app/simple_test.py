"""Simple test to check the server works"""
import asyncio
from server import mcp
from shared_state import reset_cycle

async def test_tools():
    # Reset cycle
    reset_cycle()

    # List tools
    tools = mcp._tool_manager._tools
    print(f"Available tools: {list(tools.keys())}")

    # Get the write_status tool
    write_status_tool = tools["write_status"]
    print(f"Tool type: {type(write_status_tool)}")
    print(f"Tool attributes: {dir(write_status_tool)}")

    # Try to call it using run method with arguments parameter
    try:
        result = await write_status_tool.run(arguments={
            "sensor_reading": 2000,
            "water_24h": 100.0,
            "light_today": 240.0,
            "plant_state": "healthy",
            "next_action_sequence": [{"order": 1, "action": "observe", "value": None}],
            "reasoning": "Testing"
        })
        print(f"✓ Status written result type: {type(result)}")
        print(f"✓ Status written content type: {type(result.content)}")
        print(f"✓ Status written content: {result.content}")

        # Now try reading moisture
        moisture_tool = tools["read_moisture"]
        reading = await moisture_tool.run(arguments={})
        print(f"✓ Moisture reading result type: {type(reading)}")
        print(f"✓ Moisture reading content type: {type(reading.content)}")
        print(f"✓ Moisture reading content: {reading.content}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_tools())