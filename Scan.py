import discord
from dotenv import load_dotenv
import os
from discord.ext import commands
import asyncio
import time

load_dotenv()

BOT_PREFIX = "!"

ALLOWED_USER_IDS = [
    user_id.strip()
    for user_id in os.getenv("ALLOWED", "").split(",")
    if user_id.strip()
]

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env file")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

scan_process = None


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def scan(ctx):
    global scan_process

    if ctx.author == bot.user:
        return

    if str(ctx.author.id) not in ALLOWED_USER_IDS:
        await ctx.channel.send("User not allowed.")
        return

    if scan_process and scan_process.returncode is None:
        await ctx.channel.send("A scan is already running.")
        return

    await ctx.channel.send("Starting ZMap scan...")

    # Removed -q because it hides progress/output
    command = "zmap -i tun0 --iplayer -p 443 -r 50 -q"

    scan_process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    last_send = 0
    output_buffer = []

    async def read_stream(stream, name):
        nonlocal last_send, output_buffer

        while True:
            line = await stream.readline()

            if not line:
                break

            text = line.decode(errors="replace").strip()

            if not text:
                continue

            print(f"[{name}] {text}")

            output_buffer.append(text)

            now = time.time()

            # Send output every 5 seconds to avoid Discord rate limits
            if now - last_send >= 5:
                last_send = now

                message = "\n".join(output_buffer[-15:])

                if len(message) > 1900:
                    message = message[-1900:]

                await ctx.channel.send(f"```text\n{message}\n```")

    await asyncio.gather(
        read_stream(scan_process.stdout, "STDOUT"),
        read_stream(scan_process.stderr, "STDERR")
    )

    return_code = await scan_process.wait()

    if output_buffer:
        final_output = "\n".join(output_buffer[-20:])

        if len(final_output) > 1900:
            final_output = final_output[-1900:]

        await ctx.channel.send(
            f"ZMap finished with code `{return_code}`.\n"
            f"Final output:\n```text\n{final_output}\n```"
        )
    else:
        await ctx.channel.send(f"ZMap finished with code `{return_code}`, but no output was captured.")

    scan_process = None


@bot.command()
async def stop(ctx):
    global scan_process

    if str(ctx.author.id) not in ALLOWED_USER_IDS:
        await ctx.channel.send("User not allowed.")
        return

    if scan_process and scan_process.returncode is None:
        scan_process.terminate()
        await ctx.channel.send("Scanning ended.")
    else:
        await ctx.channel.send("No scan is currently running.")


bot.run(TOKEN)