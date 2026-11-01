"""Version-checked textual adapter; imports no board runtime."""
def _patch_menu(source):
    source=source.replace('\r\n','\n')
    if '# Z20_VISUAL_MENU_V1' in source:return source
    anchor='            self.controller=EyeDeviceController(device_link,time.monotonic(),direction_idle_enabled=direction_idle_enabled)'
    if source.count(anchor)!=1:raise ValueError('unknown system_hdmi controller baseline')
    source=source.replace(anchor,anchor+'''
            # Z20_VISUAL_MENU_V1
            from z20_compute.z15_visual_menu import attach_from_environment,VISUAL_LABELS
            self.controller=attach_from_environment(self.controller,device_link,BASE,direction_idle_enabled=direction_idle_enabled)
            if hasattr(self.controller,'visual_client'):
                shell_cache=None  # Build the expanded menu before first presentation; retain the original cache.
                page_policy.PAGES=page_policy.PAGES | frozenset(VISUAL_LABELS)
                ICONS.update({page:('previous','return','next') for page in VISUAL_LABELS})
''')
    anchor="            if page=='drive':\n                self.paint_frequencies"
    if source.count(anchor)!=1:raise ValueError('unknown system_hdmi render baseline')
    return source.replace(anchor,"""            if hasattr(state,'visual_client') and page in ('media','visual_sources','z20_menu','z20_active'):
                for box,label in zip(BOXES,state.labels()):
                    rounded_box(draw,box,24,CARD,OUTLINE,2)
                    centered_text(rgb,self.renderer,label,box,44)
            if page=='drive':
                self.paint_frequencies""")


def patch_hdmi(source):
    source=_patch_menu(source)
    marker='# Z20_DEVICE_FEEDBACK_V1'
    if marker in source:return source
    # New device pages own their stop/return state and feedback together.
    if "line=device_view['message']" in source and 'state.device_presentation()' in source:
        return source
    anchor="                line=devices['message']"
    if source.count(anchor)!=1:raise ValueError('unknown device feedback baseline')
    return source.replace(anchor,"""                # Z20_DEVICE_FEEDBACK_V1
                from z20_compute.z15_visual_menu import device_status_text
                line=device_status_text(devices)""",1)
