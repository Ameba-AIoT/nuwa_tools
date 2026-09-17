<div align="center">

# nuwa_tools — Ameba Zephyr SDK Tooling

**CLI and host utilities for the [Nuwa Zephyr SDK](https://github.com/Ameba-AIoT/nuwa).**

</div>

`nuwa_tools` provides the `nuwa.py` CLI — a wrapper around `west` that handles toolchain setup, building, flashing, and monitoring. It also bundles host-side utilities for flashing and tracing.

## nuwa.py Commands

| Command   | Description |
|:--------- |:----------- |
| `build`   | Build application for a specific board |
| `flash`   | Flash firmware to the board |
| `monitor` | Start serial output monitor |
| `update`  | Update the SDK workspace |
| `setup`   | Set up the SDK workspace (install toolchain and dependencies) |
| `config`  | Configure the SDK |
| `query`   | Query SDK information (boards, toolchain, …) |
| `twister` | Run Zephyr Twister with Ameba toolchain auto-resolved |

Run `./nuwa.py <command> --help` for options.

## Structure

```
tools/
├── meta_tools/
│   └── nuwa.py             unified CLI entry point
├── scripts/                build helpers, image processing, GDB and menuconfig integration
└── ameba/
    ├── ImageTool/          GUI flash utility (Windows)
    ├── RemoteService/      remote serial server for Linux → Windows flashing
    └── TraceTool/          serial trace capture tool
```

## Usage

This repository is fetched automatically when initializing the Nuwa SDK:

```bash
west init -m https://github.com/Ameba-AIoT/nuwa.git && west update
ln -sf tools/meta_tools/nuwa.py nuwa.py
```

See the [Nuwa SDK](https://github.com/Ameba-AIoT/nuwa) for full documentation.
