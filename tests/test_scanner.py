"""Tests for configuration persistence, XML schema parsing, and client interactions."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hpscancli.config import AppConfig
from hpscancli.models import ScannerCapabilities, ScanOptions
from hpscancli.schema import (
    build_scan_xml,
    parse_job_status,
    parse_scanner_capabilities,
)
from hpscancli.client import HPScannerClient
from hpscancli.exceptions import FileExistsError, ScannerConnectionError, ScannerJobError


SAMPLE_CAPABILITIES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<scan:ScannerCapabilities xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03" xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
    <pwg:MakeAndModel>HP LaserJet MFP M234sdw</pwg:MakeAndModel>
    <pwg:SerialNumber>CN12345678</pwg:SerialNumber>
    <scan:Manufacturer>HP</scan:Manufacturer>
    <pwg:Version>2.6</pwg:Version>
    <scan:Platen>
        <scan:MinWidth>0</scan:MinWidth>
        <scan:MaxWidth>2550</scan:MaxWidth>
        <scan:MinHeight>0</scan:MinHeight>
        <scan:MaxHeight>3508</scan:MaxHeight>
        <scan:ColorMode>RGB24</scan:ColorMode>
        <scan:ColorMode>Grayscale8</scan:ColorMode>
        <pwg:DocumentFormat>application/pdf</pwg:DocumentFormat>
        <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
        <pwg:DocumentFormat>image/png</pwg:DocumentFormat>
        <scan:DiscreteResolution>
            <scan:XResolution>150</scan:XResolution>
            <scan:YResolution>150</scan:YResolution>
        </scan:DiscreteResolution>
        <scan:DiscreteResolution>
            <scan:XResolution>300</scan:XResolution>
            <scan:YResolution>300</scan:YResolution>
        </scan:DiscreteResolution>
        <scan:DiscreteResolution>
            <scan:XResolution>600</scan:XResolution>
            <scan:YResolution>600</scan:YResolution>
        </scan:DiscreteResolution>
    </scan:Platen>
    <scan:Adf>
        <scan:AdfSimplexInputCaps/>
    </scan:Adf>
</scan:ScannerCapabilities>
"""

SAMPLE_STATUS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<scan:ScannerStatus xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03" xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
    <pwg:Version>2.1</pwg:Version>
    <scan:Jobs>
        <scan:JobInfo>
            <pwg:JobUri>/eSCL/ScanJobs/job-42</pwg:JobUri>
            <pwg:JobState>Processing</pwg:JobState>
        </scan:JobInfo>
    </scan:Jobs>
</scan:ScannerStatus>
"""


def test_config_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "config.json"

        # Initially non-existent -> returns defaults
        cfg = AppConfig.load(cfg_file)
        assert cfg.ip is None
        assert cfg.default_dpi == 300

        # Save new values
        cfg.ip = "192.168.1.50"
        cfg.default_dpi = 600
        cfg.default_format = "pdf"
        saved_path = cfg.save(cfg_file)
        assert saved_path == cfg_file

        # Load back
        loaded = AppConfig.load(cfg_file)
        assert loaded.ip == "192.168.1.50"
        assert loaded.default_dpi == 600
        assert loaded.default_format == "pdf"


def test_parse_scanner_capabilities():
    caps = parse_scanner_capabilities(SAMPLE_CAPABILITIES_XML)
    assert caps.make_and_model == "HP LaserJet MFP M234sdw"
    assert caps.serial_number == "CN12345678"
    assert caps.manufacturer == "HP"
    assert caps.min_width == 0
    assert caps.max_width == 2550
    assert caps.max_height == 3508
    assert caps.color_modes == ["RGB24", "Grayscale8"]
    assert caps.document_formats == ["application/pdf", "image/jpeg", "image/png"]
    assert caps.supported_resolutions == [150, 300, 600]
    assert caps.adf_supported is True


def test_build_scan_xml():
    xml = build_scan_xml(
        width=2550,
        height=3508,
        xdpi=300,
        ydpi=300,
        colormode="RGB24",
        format_type="application/pdf",
    )
    assert "<pwg:Height>3508</pwg:Height>" in xml
    assert "<pwg:Width>2550</pwg:Width>" in xml
    assert "<scan:XResolution>300</scan:XResolution>" in xml
    assert "<scan:ColorMode>RGB24</scan:ColorMode>" in xml
    assert "<scan:DocumentFormatExt>application/pdf</scan:DocumentFormatExt>" in xml


def test_parse_job_status():
    job_uri = parse_job_status(SAMPLE_STATUS_XML)
    assert job_uri == "/eSCL/ScanJobs/job-42"


def test_resolve_output_path():
    client = HPScannerClient("192.168.1.50")
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / "output.png"

        # Resolves correct extension
        resolved = client.resolve_output_path(str(Path(tmpdir) / "output"), "image/png")
        assert resolved.name == "output.png"

        # Destination exists without overwrite -> raises FileExistsError
        dest.write_text("existing")
        with pytest.raises(FileExistsError):
            client.resolve_output_path(str(dest), "image/png", overwrite=False)

        # Destination exists with overwrite -> succeeds
        resolved_overwrite = client.resolve_output_path(str(dest), "image/png", overwrite=True)
        assert resolved_overwrite == dest


def test_client_get_capabilities():
    client = HPScannerClient("192.168.1.50")
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_CAPABILITIES_XML
        mock_get.return_value = mock_resp

        caps = client.get_capabilities()
        assert caps.make_and_model == "HP LaserJet MFP M234sdw"


def test_client_create_scan_job_with_location_header():
    client = HPScannerClient("192.168.1.50")
    caps = parse_scanner_capabilities(SAMPLE_CAPABILITIES_XML)

    with patch.object(client.session, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.headers = {"Location": "http://192.168.1.50/eSCL/ScanJobs/job-101"}
        mock_post.return_value = mock_resp

        opts = ScanOptions(ip="192.168.1.50", dpi=300)
        job_url = client.create_scan_job(opts, capabilities=caps)
        assert job_url == "http://192.168.1.50/eSCL/ScanJobs/job-101"


def test_client_download_scanned_document():
    client = HPScannerClient("192.168.1.50")
    with tempfile.TemporaryDirectory() as tmpdir:
        out_target = Path(tmpdir) / "output.pdf"

        with patch.object(client.session, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_content.return_value = [b"%PDF-1.4 sample pdf content"]
            mock_get.return_value = mock_resp

            saved = client.download_scanned_document("http://192.168.1.50/eSCL/ScanJobs/job-101", destination=out_target)
            assert saved == out_target
            assert out_target.read_bytes() == b"%PDF-1.4 sample pdf content"


def test_client_scan_png_fallback_with_pillow():
    # Capabilities without native PNG support (like HP Smart Tank 510)
    caps_xml_no_png = """<?xml version="1.0" encoding="UTF-8"?>
    <scan:ScannerCapabilities xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03" xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
        <pwg:MakeAndModel>Smart Tank 510</pwg:MakeAndModel>
        <scan:Platen>
            <pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>
            <pwg:DocumentFormat>application/pdf</pwg:DocumentFormat>
        </scan:Platen>
    </scan:ScannerCapabilities>
    """
    client = HPScannerClient("192.168.1.50")

    # Generate a tiny 1x1 valid JPEG to simulate scanner output
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_target = Path(tmpdir) / "output.png"

        with patch.object(client, "get_capabilities", return_value=parse_scanner_capabilities(caps_xml_no_png)), \
             patch.object(client, "create_scan_job", return_value="http://192.168.1.50/eSCL/ScanJobs/job-102"), \
             patch.object(client.session, "get") as mock_get:

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = jpeg_bytes
            mock_resp.iter_content.return_value = [jpeg_bytes]
            mock_get.return_value = mock_resp

            opts = ScanOptions(ip="192.168.1.50", format="image/png", output_path=str(out_target))
            saved = client.scan(opts)

            assert saved == out_target
            assert out_target.exists()

            # Verify saved file is a valid PNG
            with Image.open(out_target) as img:
                assert img.format == "PNG"


def test_cli_subcommands():
    from hpscancli.cli import parse_args

    args_scan = parse_args(["scan", "-i", "10.0.0.1", "--png", "-o", "doc1"])
    assert args_scan.command == "scan"
    assert args_scan.ip == "10.0.0.1"
    assert args_scan.png is True
    assert args_scan.output == "doc1"

    args_bulk = parse_args(["bulkscan", "-i", "10.0.0.1", "--dpi", "300"])
    assert args_bulk.command == "bulkscan"
    assert args_bulk.ip == "10.0.0.1"
    assert args_bulk.dpi == 300


def test_invalid_dpi_raises_error():
    from hpscancli.exceptions import InvalidParameterError
    client = HPScannerClient("192.168.1.50")
    caps = parse_scanner_capabilities(SAMPLE_CAPABILITIES_XML)
    # SAMPLE_CAPABILITIES_XML has supported resolutions [150, 300, 600]
    opts = ScanOptions(ip="192.168.1.50", dpi=999)
    with pytest.raises(InvalidParameterError) as exc_info:
        client.create_scan_job(opts, capabilities=caps)
    assert "Requested DPI '999' is not supported" in str(exc_info.value)


def test_colormode_normalization():
    from hpscancli.cli import normalize_colormode
    assert normalize_colormode("color") == "RGB24"
    assert normalize_colormode("COLOR") == "RGB24"
    assert normalize_colormode("bw") == "Grayscale8"
    assert normalize_colormode("BW") == "Grayscale8"
    assert normalize_colormode("RGB24") == "RGB24"
    assert normalize_colormode("Grayscale8") == "Grayscale8"


def test_cli_config_subcommands(capsys):
    from hpscancli.cli import handle_config, parse_args

    cfg = AppConfig(ip="192.168.1.10", default_dpi=150, default_format="pdf", default_colormode="RGB24")

    # config show
    args_show = parse_args(["config", "show"])
    handle_config(args_show, cfg)
    out = capsys.readouterr().out
    assert "ip        : 192.168.1.10" in out
    assert "dpi       : 150" in out

    # config get ip
    args_get = parse_args(["config", "get", "ip"])
    handle_config(args_get, cfg)
    assert capsys.readouterr().out.strip() == "192.168.1.10"

    # config set
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_cfg_file = Path(tmpdir) / "config.json"
        with patch("hpscancli.cli.get_default_config_dir", return_value=Path(tmpdir)):
            args_set_ip = parse_args(["config", "set", "ip", "10.0.0.99"])
            handle_config(args_set_ip, cfg)
            assert cfg.ip == "10.0.0.99"

            args_set_dpi = parse_args(["config", "set", "dpi", "600"])
            handle_config(args_set_dpi, cfg)
            assert cfg.default_dpi == 600

            args_set_fmt = parse_args(["config", "set", "format", "png"])
            handle_config(args_set_fmt, cfg)
            assert cfg.default_format == "png"

            args_set_cm = parse_args(["config", "set", "colormode", "bw"])
            handle_config(args_set_cm, cfg)
            assert cfg.default_colormode == "Grayscale8"


def test_cli_bulkscan_flags():
    from hpscancli.cli import parse_args

    args_bulk = parse_args(["bulkscan", "-i", "10.0.0.1"])
    assert args_bulk.command == "bulkscan"
    assert args_bulk.split is False

    args_split = parse_args(["bulkscan", "-i", "10.0.0.1", "--split"])
    assert args_split.command == "bulkscan"
    assert args_split.split is True




