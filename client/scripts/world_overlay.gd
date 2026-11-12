extends Node2D
## Screen-space layer above geography: game plots, sprites and settlement labels.
func _draw() -> void:
    get_parent().draw_overlay(self)
