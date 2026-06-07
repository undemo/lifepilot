def looks_solo_mood_relief(raw_text: str) -> bool:
    if any(token in raw_text for token in ("朋友", "同学", "老婆", "孩子", "亲子", "纪念日", "约会")):
        return False
    solo_signal = "一个人" in raw_text or "自己" in raw_text or "独自" in raw_text
    mood_signal = any(token in raw_text for token in ("难受", "烦", "低落", "累", "不开心", "难过", "emo", "散心", "散散心", "放松", "失恋", "情绪", "心情"))
    light_outing_signal = any(token in raw_text for token in ("转转", "溜一圈", "走走", "附近", "金沙湖", "逛", "音乐", "喝酒", "小酌", "酒吧", "酒馆"))
    explicit_light_walk = any(token in raw_text for token in ("溜一圈", "走走", "转转"))
    light_drink_signal = any(token in raw_text for token in ("喝酒", "喝点酒", "喝杯酒", "喝一杯", "小酌", "清吧", "酒吧"))
    return solo_signal or (mood_signal and light_outing_signal) or explicit_light_walk or (mood_signal and light_drink_signal)
