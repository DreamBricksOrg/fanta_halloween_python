from portrait_player.app import portrait_viewport_size


def test_portrait_viewport_preserves_9_by_16_ratio_on_landscape_screen():
    assert portrait_viewport_size(1920, 1080) == (607, 1080)


def test_portrait_viewport_fills_portrait_screen_without_distortion():
    assert portrait_viewport_size(1080, 1920) == (1080, 1920)
