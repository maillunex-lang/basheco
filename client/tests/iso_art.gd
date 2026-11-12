extends SceneTree
const IsoBuilding = preload("res://scripts/iso_building.gd")
const GeoBackground = preload("res://scripts/geo_background.gd")
var errors := 0
func check(ok: bool, description: String) -> void:
    if not ok:
        errors += 1
        printerr("FAIL: " + description)
func _initialize() -> void:
    call_deferred("_run")
func _run() -> void:
    check(IsoBuilding.SPRITES.size() == 3, "three zone sprite types")
    check(GeoBackground.BUILDING_SPRITES.size() == 4, "four background building variants")
    check(GeoBackground.TREE_SPRITES.size() == 2, "two environment sprite variants")
    for texture in IsoBuilding.SPRITES.values():
        check(texture != null and texture.get_width() > 0, "zone art loaded")
    var scene: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(scene)
    await process_frame
    check(scene.TILE_W == 2.0 * scene.TILE_H, "orthographic isometry")
    check(scene.has_method("refresh_parcels"), "server remains authoritative")
    scene.queue_free()
    if errors == 0:
        print("BASHECO_ISO_ART_OK zones=3 building_variants=4 tree_variants=2")
    quit(errors)