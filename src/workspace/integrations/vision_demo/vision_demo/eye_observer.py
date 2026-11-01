"""Keep native eye protocol state current while image mode consumes no gaze actions."""
class _PassiveController:
    def __init__(self,controller):self.controller=controller
    def __getattr__(self,name):return getattr(self.controller,name)
    def gaze(self,event,now):pass

def can_enter(eye):
    return eye is None or eye.guide.phase in ('selection','failed')

def observe_eye(eye,controller,now):
    return eye.poll(_PassiveController(controller),now)
