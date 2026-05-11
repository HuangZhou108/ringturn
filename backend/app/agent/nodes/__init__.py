from .fetch_source import fetch_source_node
from .analyze_structure import analyze_structure_node
from .extract_melody import extract_melody_node
from .generate_midi import generate_midi_node
from .arrange import arrange_node
from .render import render_node
from .check_quality import check_quality_node
from app.agent.state import TaskStep

NODE_HANDLERS = {
    TaskStep.FETCH_SOURCE.value: fetch_source_node,
    TaskStep.ANALYZE_STRUCTURE.value: analyze_structure_node,
    TaskStep.EXTRACT_MELODY.value: extract_melody_node,
    TaskStep.GENERATE_MIDI.value: generate_midi_node,
    TaskStep.ARRANGE.value: arrange_node,
    TaskStep.RENDER.value: render_node,
    TaskStep.CHECK_QUALITY.value: check_quality_node,
}