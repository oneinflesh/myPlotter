from myplotter.plot.job import PlotJob


def estimate_seconds(drawing, steps_per_mm, speed_mm_s, geometry):
    planner = PlotJob(None, drawing, steps_per_mm, speed_mm_s, geometry, (0, 0))
    total_ms = 0
    for motion in planner._motions():
        if motion.checkpoint:
            total_ms += 2000
            continue
        parts = motion.command.split(",")
        total_ms += int(parts[2] if parts[0] == "SP" else parts[1])
    return total_ms / 1000


def format_duration(seconds):
    minutes, seconds = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"
