from ass_parser import AssEvent

__all__ = ("incr_layer", "reset_layer")


def incr_layer(ev: AssEvent, inc: int = 0):
    if ev.is_comment:
        return
    ev.layer += inc


def reset_layer(ev: AssEvent):
    if ev.is_comment:
        return
    ev.layer = 0
