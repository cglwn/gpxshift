from pathlib import Path

from gpxshift import GPXShiftApp


def _make_sample_gpx(time_str: str) -> str:
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<gpx version=\"1.1\" creator=\"pytest\" xmlns=\"http://www.topografix.com/GPX/1/1\">
  <trk>
    <name>Test Track</name>
    <trkseg>
      <trkpt lat=\"0\" lon=\"0\">
        <ele>0</ele>
        <time>{time_str}</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
"""


def test_shift_back_14_hours(tmp_path):
    fixtures_dir = Path(__file__).parent / "fixtures"
    input_path = fixtures_dir / "cn_tower_sample.gpx"
    expected_path = fixtures_dir / "cn_tower_sample_shifted_minus14h.gpx"

    app = GPXShiftApp(str(input_path))
    app.shift_time(-14)
    output_path = tmp_path / "shifted.gpx"
    app.save_gpx(str(output_path))

    assert output_path.read_text() == expected_path.read_text()


def test_default_output_filename_positive_shift(tmp_path):
    input_path = tmp_path / "morning_run.gpx"
    input_path.write_text(_make_sample_gpx("2025-01-01T00:00:00Z"))

    app = GPXShiftApp(str(input_path))
    app.shift_time(3)

    default_path = app.get_default_output_path()
    assert default_path == tmp_path / "morning_run_p3.gpx"

    saved_path = app.save_gpx()
    assert saved_path == default_path
    assert saved_path.exists()
    assert "<time>2025-01-01T03:00:00Z</time>" in saved_path.read_text()


def test_default_output_filename_negative_shift(tmp_path):
    input_path = tmp_path / "evening_run.gpx"
    input_path.write_text(_make_sample_gpx("2025-01-01T12:00:00Z"))

    app = GPXShiftApp(str(input_path))
    app.shift_time(-2)

    default_path = app.get_default_output_path()
    assert default_path == tmp_path / "evening_run_m2.gpx"

    saved_path = app.save_gpx()
    assert saved_path == default_path
    assert saved_path.exists()
    assert "<time>2025-01-01T10:00:00Z</time>" in saved_path.read_text()
