from __future__ import annotations

from typer.testing import CliRunner

from code_analyzer_core.cli import app
from code_analyzer_core.scanners.java_syntax import parse_java_text, tree_sitter_available
from code_analyzer_core.scanners.java_scanner import scan_java_files
from code_analyzer_core.models import Direction, InterfaceKind


def test_tree_sitter_provider_extracts_class_method_annotations_fields(tmp_path):
    src = tmp_path / "BookingController.java"
    src.write_text(
        '''
        package demo.booking;
        import org.springframework.web.bind.annotation.*;
        @RestController
        @RequestMapping("/booking")
        class BookingController {
          private final BookingService service;
          // service.create(request) must not become a method boundary or call fact by itself.
          @PostMapping(value = "/create")
          public BookingResponse create(@RequestBody BookingRequest request) {
            return service.create(request);
          }
        }
        class BookingRequest { private String bookingId; }
        class BookingResponse { private String bookingId; }
        ''',
        encoding="utf-8",
    )

    parsed = parse_java_text(src.read_text(encoding="utf-8"), src)
    controller = next(c for c in parsed.classes if c.name == "BookingController")
    method = next(m for m in controller.methods if m.name == "create")

    assert parsed.provider == "tree_sitter"
    assert parsed.package == "demo.booking"
    assert [a.name for a in controller.annotations] == ["RestController", "RequestMapping"]
    assert [a.name for a in method.annotations] == ["PostMapping"]
    assert method.params[0].name == "request"
    assert method.params[0].type == "BookingRequest"
    assert [a.name for a in method.params[0].annotations] == ["RequestBody"]
    assert method.line_start < method.line_end


def test_structural_scan_uses_tree_sitter_evidence_refs(tmp_path):
    src = tmp_path / "BookingController.java"
    src.write_text(
        '''
        @RestController
        class BookingController {
          @PostMapping("/booking")
          public BookingResponse create(@RequestBody BookingRequest request) {
            return new BookingResponse();
          }
        }
        class BookingRequest { private String bookingId; }
        class BookingResponse { private String bookingId; }
        ''',
        encoding="utf-8",
    )

    facts, schemas, interfaces, relations, mapper_facts, warnings = scan_java_files([src])

    assert not [w for w in warnings if "failed" in w.lower()]
    assert {s.name for s in schemas} >= {"BookingRequest", "BookingResponse"}
    inbound = [i for i in interfaces if i.direction == Direction.INBOUND and i.kind == InterfaceKind.REST]
    assert len(inbound) == 1
    assert inbound[0].schema_ref == "BookingRequest"
    assert inbound[0].evidence[0].extractor.startswith("java_tree_sitter")
    assert relations[0].evidence[0].extractor.startswith("java_tree_sitter")


def test_doctor_reports_tree_sitter_provider():
    ok, detail = tree_sitter_available()
    assert ok, detail
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "java_syntax_provider" in result.stdout
    assert "tree_sitter" in result.stdout


def test_tree_sitter_workspace_cache_and_annotation_helpers(tmp_path):
    from code_analyzer_core.scanners.java_syntax import (
        clear_java_syntax_cache,
        java_syntax_cache_stats,
        parse_java_files,
    )

    src = tmp_path / "AnnotatedEntity.java"
    src.write_text(
        '''
        @Table(name = "booking", uniqueConstraints = {})
        class AnnotatedEntity {
          @Column(name = "booking_id", nullable = false)
          String id;
          String getId() { return id; }
        }
        ''',
        encoding="utf-8",
    )

    clear_java_syntax_cache()
    parsed1, warnings1 = parse_java_files([src])
    parsed2, warnings2 = parse_java_files([src])

    assert warnings1 == []
    assert warnings2 == []
    assert parsed1[0] is parsed2[0]
    stats = java_syntax_cache_stats()
    assert stats["cache_misses"] == 1
    assert stats["cache_hits"] == 1

    cls = parsed1[0].classes[0]
    assert cls.annotations[0].string_arg("name") == "booking"
    col = cls.fields[0].annotations[0]
    assert col.string_arg("name") == "booking_id"
    assert col.bool_arg("nullable") is False
