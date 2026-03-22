"""nodeforge-agent: server-side execution engine.

The agent runs on the managed server and executes plans locally.
It is installed as the first step of every bootstrap and subsequently
handles all provisioning operations without requiring SSH round-trips
for each command.
"""
