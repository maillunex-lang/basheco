        var min_tile: Vector2 = item["minimum"]
        var max_tile: Vector2 = item["maximum"]
        if max_tile.x < visible_bounds[0] or max_tile.y < visible_bounds[1] or min_tile.x > visible_bounds[2] or min_tile.y > visible_bounds[3]:
            continue
        var points := PackedVector2Array()
        for tile in item["tiles"]:
            points.append(world.project_point(tile.x, tile.y))
          var min_tile: Vector2 = item["minimum"]
          var max_tile: Vector2 = item["maximum"]
          if max_tile.x < visible_bounds[0] or max_tile.y < visible_bounds[1] or min_tile.x > visible_bounds[2] or min_tile.y > visible_bounds[3]:
              continue
          var points := PackedVector2Array()
          for tile in item["tiles"]:
              points.append(world.project_point(tile.x, tile.y))
          match kind:
              "road":
                  world.draw_polyline(points, Color("#293d44", 0.95), maxf(3.0, 7.0 * world.zoom_level), true)
                  world.draw_polyline(points, Color("#8d9391", 0.95), maxf(2.0, 5.0 * world.zoom_level), true)
                  if world.zoom_level > 1.45:
                      world.draw_polyline(points, Color("#d7d1b5", 0.5), 1.0, true)
              "building":
                  if points.size() >= 3 and points[0].distance_to(points[points.size() - 1]) < 1.0:
                      world.draw_colored_polygon(points, Color("#a9b7ae", 0.3))
                  world.draw_polyline(points, Color("#b6c6cb", 0.65), 1.0, true)
                  if buildings_drawn < MAX_VISIBLE_BUILDINGS and world.zoom_level >= 0.85:
                      var center := (min_tile + max_tile) * 0.5
                      var anchor: Vector2 = world.project_point(center.x, center.y)
                      var footprint := maxf(max_tile.x - min_tile.x, max_tile.y - min_tile.y)
                      var width := clampf(footprint * 9.0 * world.zoom_level, 22.0, 68.0)
                      var index := posmod(int(absf(center.x * 17.0 + center.y * 31.0)), BUILDING_SPRITES.size())
                      var texture: Texture2D = BUILDING_SPRITES[index]
                      var height := width * float(texture.get_height()) / float(texture.get_width())
                      world.draw_texture_rect(texture, Rect2(anchor.x - width * 0.5, anchor.y - height * 0.78, width, height), false)
                      buildings_drawn += 1
              "water":
                  if points.size() >= 3 and points[0].distance_to(points[points.size() - 1]) < 1.0:
                      world.draw_colored_polygon(points, Color("#327fa8", 0.65))
                  world.draw_polyline(points, Color("#4a9cc7", 0.9), 2.0, true)
              "forest":
                  if points.size() >= 3 and points[0].distance_to(points[points.size() - 1]) < 1.0:
                      world.draw_colored_polygon(points, Color("#36734c", 0.3))
                  world.draw_polyline(points, Color("#4b9164", 0.8), 2.0, true)
                  # Deterministic visual tree symbols inside mapped OSM forest polygons.
                  if trees_drawn < MAX_VISIBLE_TREES and world.zoom_level >= 0.85:
                      var tiles: PackedVector2Array = item["tiles"]
                      var step := 8.0
                      for gx in range(int(ceil(min_tile.x / step)), int(floor(max_tile.x / step)) + 1):
                          for gy in range(int(ceil(min_tile.y / step)), int(floor(max_tile.y / step)) + 1):
                              if trees_drawn >= MAX_VISIBLE_TREES:
                                  break
                              var tile := Vector2(float(gx) * step, float(gy) * step)
                              if not Geometry2D.is_point_in_polygon(tile, tiles):
                                  continue
                              var anchor: Vector2 = world.project_point(tile.x, tile.y)
                              var width := 20.0 * world.zoom_level
                              var height := width * float(TREE_SPRITE.get_height()) / float(TREE_SPRITE.get_width())
                              world.draw_texture_rect(TREE_SPRITE, Rect2(anchor.x - width * 0.5, anchor.y - height, width, height), false)
                              trees_drawn += 1
              "farmland":
                  if points.size() >= 3 and points[0].distance_to(points[points.size() - 1]) < 1.0:
                      world.draw_colored_polygon(points, Color("#a3ad63", 0.24))
                  world.draw_polyline(points, Color("#a3ad63", 0.8), 2.0, true)
