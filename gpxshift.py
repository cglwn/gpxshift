import argparse
import datetime
import io
import os
import re
import sys
import termios
import tty
from pathlib import Path

import gpxpy
import gpxpy.gpx

from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text


def utc_to_local(utc_dt):
    if not utc_dt:
        return None
    return utc_dt.replace(tzinfo=datetime.timezone.utc).astimezone(tz=None)


GPX_TIME_PATTERN = re.compile(
    r"(<time>)(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)(</time>)"
)


def shift_gpx_times(gpx_text, shift_delta):
    if not shift_delta or shift_delta == datetime.timedelta(0):
        return gpx_text

    def _replace(match):
        timestamp_str = match.group(2)
        timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
        timestamp = timestamp.replace(tzinfo=datetime.timezone.utc) + shift_delta
        return f"{match.group(1)}{timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')}{match.group(3)}"

    return GPX_TIME_PATTERN.sub(_replace, gpx_text)


class GPXShiftApp:
    def __init__(self, gpx_file_path):
        self.gpx_file_path = str(gpx_file_path)
        self.original_gpx_path = Path(self.gpx_file_path)
        self.original_gpx_text = self.original_gpx_path.read_text()
        self.original_gpx = self._parse_gpx_text(self.original_gpx_text)
        self.current_gpx = self._parse_gpx_text(
            self.original_gpx_text
        ) 
        self.time_shift = datetime.timedelta(hours=0)
        self.display_utc = False

    def _parse_gpx_text(self, gpx_text):
        return gpxpy.parse(io.StringIO(gpx_text))

    def get_start_end_times(self, gpx_data):
        time_bounds = gpx_data.get_time_bounds()
        if time_bounds:
            return time_bounds.start_time, time_bounds.end_time
        return None, None

    def shift_time(self, hours):
        self.time_shift += datetime.timedelta(hours=hours)
        self.current_gpx = self._apply_shift(self.original_gpx, self.time_shift)

    def toggle_display_mode(self):
        self.display_utc = not self.display_utc

    def get_shift_hours(self):
        return int(self.time_shift.total_seconds() // 3600)

    def get_default_output_path(self):
        hours = self.get_shift_hours()
        sign = "p" if hours >= 0 else "m"
        suffix = f"_{sign}{abs(hours)}"
        stem = self.original_gpx_path.stem
        extension = self.original_gpx_path.suffix or ""
        return self.original_gpx_path.with_name(f"{stem}{suffix}{extension}")

    def _apply_shift(self, gpx_data, shift_delta):
        shifted_gpx = gpxpy.gpx.GPX()
        shifted_gpx.creator = gpx_data.creator
        shifted_gpx.version = gpx_data.version

        for track in gpx_data.tracks:
            new_track = gpxpy.gpx.GPXTrack()
            new_track.name = track.name
            for segment in track.segments:
                new_segment = gpxpy.gpx.GPXTrackSegment()
                for point in segment.points:
                    new_point = gpxpy.gpx.GPXTrackPoint(
                        latitude=point.latitude,
                        longitude=point.longitude,
                        elevation=point.elevation,
                        time=point.time + shift_delta if point.time else None,
                    )
                    new_segment.points.append(new_point)
                new_track.segments.append(new_segment)
            shifted_gpx.tracks.append(new_track)

        for waypoint in gpx_data.waypoints:
            new_waypoint = gpxpy.gpx.GPXWaypoint(
                latitude=waypoint.latitude,
                longitude=waypoint.longitude,
                elevation=waypoint.elevation,
                time=waypoint.time + shift_delta if waypoint.time else None,
            )
            new_waypoint.name = waypoint.name
            shifted_gpx.waypoints.append(new_waypoint)

        for route in gpx_data.routes:
            new_route = gpxpy.gpx.GPXRoute()
            new_route.name = route.name
            for point in route.points:
                new_route_point = gpxpy.gpx.GPXRoutePoint(
                    latitude=point.latitude,
                    longitude=point.longitude,
                    elevation=point.elevation,
                    time=point.time + shift_delta if point.time else None,
                )
                new_route.points.append(new_route_point)
            shifted_gpx.routes.append(new_route)

        return shifted_gpx

    def save_gpx(self, output_file_path=None):
        if output_file_path:
            candidate_path = Path(os.path.expanduser(output_file_path))
            if candidate_path.is_absolute():
                output_path = candidate_path
            elif candidate_path.parent == Path("."):
                output_path = self.original_gpx_path.parent / candidate_path.name
            else:
                output_path = Path.cwd() / candidate_path
        else:
            output_path = self.get_default_output_path()
        shifted_text = shift_gpx_times(self.original_gpx_text, self.time_shift)
        output_path.write_text(shifted_text)
        return output_path


def format_timedelta(td):
    total_seconds = int(td.total_seconds())
    sign = "-" if total_seconds < 0 else "+"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{sign}{hours:02}:{minutes:02}:{seconds:02}"


def make_layout(app):
    original_start_utc, original_end_utc = app.get_start_end_times(app.original_gpx)
    current_start_utc, current_end_utc = app.get_start_end_times(app.current_gpx)

    if app.display_utc:
        original_start_display = original_start_utc
        original_end_display = original_end_utc
        current_start_display = current_start_utc
        current_end_display = current_end_utc
        time_zone_label = " (UTC)"
    else:
        original_start_display = utc_to_local(original_start_utc)
        original_end_display = utc_to_local(original_end_utc)
        current_start_display = utc_to_local(current_start_utc)
        current_end_display = utc_to_local(current_end_utc)
        time_zone_label = " (Local)"

    layout = Layout(name="root")

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="times", ratio=2),
        Layout(name="controls", size=5),
    )

    layout["times"].split_row(Layout(name="original"), Layout(name="shifted"))

    header_content = Align.center(
        Text(
            f"GPX Time Shifter - {os.path.basename(app.gpx_file_path)}",
            style="bold white",
        ),
        vertical="middle",
    )
    layout["header"].update(Panel(header_content, style="blue"))

    original_text = Text()
    original_text.append(f"Original Times{time_zone_label}\n", style="bold cyan")
    original_text.append(
        f"Start: {original_start_display.strftime('%Y-%m-%d %H:%M:%S') if original_start_display else 'N/A'}\n"
    )
    original_text.append(
        f"End:   {original_end_display.strftime('%Y-%m-%d %H:%M:%S') if original_end_display else 'N/A'}"
    )
    layout["original"].update(
        Panel(original_text, title="[cyan]Original[/cyan]", border_style="cyan")
    )

    shifted_text = Text()
    shifted_text.append(f"Shifted Times{time_zone_label}\n", style="bold magenta")
    shifted_text.append(
        f"Start: {current_start_display.strftime('%Y-%m-%d %H:%M:%S') if current_start_display else 'N/A'}\n"
    )
    shifted_text.append(
        f"End:   {current_end_display.strftime('%Y-%m-%d %H:%M:%S') if current_end_display else 'N/A'}\n"
    )
    shifted_text.append(
        f"Total Shift: {format_timedelta(app.time_shift)}", style="bold yellow"
    )
    layout["shifted"].update(
        Panel(shifted_text, title="[magenta]Current[/magenta]", border_style="magenta")
    )

    controls_text = Text()
    controls_text.append("Controls: ", style="bold green")
    controls_text.append(
        "+ or = : Forward 1h  |  - or _ : Backward 1h  |  s : Save  |  q : Quit  |  t : Toggle UTC/Local"
    )
    layout["controls"].update(
        Panel(controls_text, title="[green]Help[/green]", border_style="green")
    )

    return layout


def _getch():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def main():
    console = Console()
    parser = argparse.ArgumentParser(description="Shift GPX file timestamps.")
    parser.add_argument("gpx_file", help="Path to the GPX file.")
    args = parser.parse_args()

    if not os.path.exists(args.gpx_file):
        console.print(
            f"[bold red]Error:[/bold red] GPX file not found at {args.gpx_file}"
        )
        sys.exit(1)

    app = GPXShiftApp(args.gpx_file)

    with Live(
        make_layout(app), console=console, screen=True, auto_refresh=False
    ) as live:
        while True:
            key = _getch()

            if key in ("+", "="):
                app.shift_time(1)
                live.update(make_layout(app))
                live.refresh()
            elif key in ("-", "_"):
                app.shift_time(-1)
                live.update(make_layout(app))
                live.refresh()
            elif key == "s":
                live.stop()
                console.clear()
                default_output_path = app.get_default_output_path()
                default_display_name = default_output_path.name
                output_filename = Prompt.ask(
                    "Enter output filename (press Enter for default)",
                    default=default_display_name,
                )
                user_choice = output_filename.strip() if output_filename else ""
                if user_choice:
                    try:
                        saved_path = app.save_gpx(user_choice)
                        console.print(f"[bold green]Saved to[/bold green] {saved_path}")
                    except Exception as e:
                        console.print(f"[bold red]Error saving:[/bold red] {e}")
                else:
                    console.print("[yellow]Save cancelled.[/yellow]")
                console.input("Press Enter to continue...")
                live.start()
                live.update(make_layout(app))
            elif key == "q":
                break
            elif key == "t":
                app.toggle_display_mode()
                live.update(make_layout(app))


if __name__ == "__main__":
    main()
