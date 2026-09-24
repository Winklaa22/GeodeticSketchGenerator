from __future__ import annotations

from typing import Dict, List

from core.commands.base import Command
from core.commands.composite import CompositeCommand
from core.commands.generated import DeleteGeneratedCommand, MarkGeneratedCommand
from core.commands.layers import AddLayerCommand, SetLayerColorCommand
from core.commands.survey import build_survey_commands
from core.config import GenerationConfig
from core.validation import ensure_has_data, ensure_selection, resolve_layer_name
from models.point import Point


class SurveyDrawService:
    def build_command(
        self, points: Dict[int, Point], selected_numbers: List[int], config: GenerationConfig
    ) -> Command:
        return CompositeCommand(self.build_commands(points, selected_numbers, [config]))

    def build_commands(
        self, points: Dict[int, Point], selected_numbers: List[int], configs: List[GenerationConfig]
    ) -> List[Command]:
        ensure_has_data(points)
        layer_names = [resolve_layer_name(config.layer_name) for config in configs]
        ensure_selection(selected_numbers)
        draw_commands = build_survey_commands(points, selected_numbers, configs, layer_names)

        # Whatever an earlier run left for these modes goes first, so that generating
        # again updates the sketch instead of drawing a second copy over it. Modes not
        # being generated now keep theirs - this run is not about them.
        results: List[Command] = [DeleteGeneratedCommand(config.draw_mode.name for config in configs)]
        for config, layer_name, draw_command in zip(configs, layer_names, draw_commands):
            # Stamped so that generating again can clear this mode's previous output
            # instead of stacking a second copy of it on top.
            marked = MarkGeneratedCommand(config.draw_mode.name, draw_command)
            if config.layer_rgb is None:
                results.append(marked)
            else:
                results.append(
                    CompositeCommand(
                        [AddLayerCommand(layer_name), SetLayerColorCommand(layer_name, config.layer_rgb), marked]
                    )
                )
        return results
