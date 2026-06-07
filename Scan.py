import discord
from dotenv import load_dotenv
import os
from discord.ext import commands
import asyncio
import time
import signal

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

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

scan_process = None
scan_stopping = False


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


def is_allowed(ctx):
    return str(ctx.author.id) in ALLOWED_USER_IDS


@bot.command()
async def scan(ctx):
    global scan_process, scan_stopping

    if ctx.author == bot.user:
        return

    if not is_allowed(ctx):
        await ctx.channel.send("User not allowed.")
        return

    if scan_process and scan_process.returncode is None:
        await ctx.channel.send("A scan is already running.")
        return

    scan_stopping = False
    await ctx.channel.send("Starting ZMap scan...")

    command = "zmap -i tun0 --iplayer -p 443 -r 50 -q"

    try:
        scan_process = await asyncio.create_subprocess_exec(
        *shlex.split(command),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=os.setsid
    )
    except Exception as e:
        scan_process = None
        await ctx.channel.send(f"Failed to start ZMap:\n```text\n{e}\n```")
        return

    last_send = 0
    output_buffer = []

    async def read_stream(stream, name):
        nonlocal last_send, output_buffer
        global scan_stopping

        while True:
            if scan_stopping:
                break

            try:
                line = await stream.readline()
            except Exception:
                break

            if not line:
                break

            if scan_stopping:
                break

            text = line.decode(errors="replace").strip()

            if not text:
                continue

            print(f"[{name}] {text}")
            output_buffer.append(text)

            now = time.time()

            if now - last_send >= 5:
                last_send = now

                message = "\n".join(output_buffer[-15:])

                if len(message) > 1900:
                    message = message[-1900:]

                if not scan_stopping:
                    await ctx.channel.send(f"```text\n{message}\n```")

    try:
        await asyncio.gather(
            read_stream(scan_process.stdout, "STDOUT"),
            read_stream(scan_process.stderr, "STDERR")
        )

        return_code = await scan_process.wait()

        if scan_stopping:
            await ctx.channel.send("Scan stopped.")
        elif output_buffer:
            final_output = "\n".join(output_buffer[-20:])

            if len(final_output) > 1900:
                final_output = final_output[-1900:]

            await ctx.channel.send(
                f"ZMap finished with code `{return_code}`.\n"
                f"Final output:\n```text\n{final_output}\n```"
            )
        else:
            await ctx.channel.send(
                f"ZMap finished with code `{return_code}`, but no output was captured."
            )

    finally:
        scan_process = None
        scan_stopping = False


@bot.command()
async def stop(ctx):
    global scan_process, scan_stopping

    if not is_allowed(ctx):
        await ctx.channel.send("User not allowed.")
        return

    if scan_process and scan_process.returncode is None:
        scan_stopping = True

        try:
            os.killpg(os.getpgid(scan_process.pid), signal.SIGTERM)
            await ctx.channel.send("Stopping scan...")
        except ProcessLookupError:
            await ctx.channel.send("Scan already stopped.")
        except Exception as e:
            await ctx.channel.send(f"Error stopping scan:\n```text\n{e}\n```")
    else:
        await ctx.channel.send("No scan is currently running.")


bot.run(TOKEN)