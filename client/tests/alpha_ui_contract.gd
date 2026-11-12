extends SceneTree
## Contract test: marketplace uses company UUID, wallet numbers come from server.
var failures := 0

func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        printerr("FAIL: " + message)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var world: Node2D = load("res://scenes/world.tscn").instantiate()
    root.add_child(world)
    await process_frame
    var company = world.get_node("Company")
    var market = world.get_node("Market")
    var nav = world.get_node("Navigation")
    var hud = world.get_node("HUD")
    var company_id := "00000000-0000-4000-8000-000000000001"
    company.companies = [{"id": company_id, "name": "Тестовое хозяйство"}]
    company.companies_updated.emit(company.companies)
    market.company_field.select(0)
    market.quantity_field.value = 2
    var payload: Variant = JSON.parse_string(market._purchase_payload())
    check(typeof(payload) == TYPE_DICTIONARY, "purchase request JSON")
    if typeof(payload) == TYPE_DICTIONARY:
        check(payload.get("company_id") == company_id, "purchase must use UUID, not selected text")
        check(payload.get("quantity") == 2, "purchase quantity")
        check(str(payload.get("idempotency_key", "")).begins_with("buy-"), "idempotency token")
    var server_response := JSON.stringify({
        "wallets": [{"company_id": company_id, "balance_kopecks": 123456}]
    }).to_utf8_buffer()
    company._on_wallet_response(0, 200, PackedStringArray(), server_response)
    check(company.balances_label.text.contains("1234,56"), "real company wallet displayed")
    check(hud.balance_label.text.contains("1234,56"), "HUD uses server wallet")
    nav._show_section("")
    check(not world.get_node("Geography").visible, "Map tab shows map, not geography dialog")
    world.queue_free()
    if failures == 0:
        print("BASHECO_ANDROID_ALPHA_UI_OK market_uuid=1 wallet=1 map_navigation=1")
    quit(failures)