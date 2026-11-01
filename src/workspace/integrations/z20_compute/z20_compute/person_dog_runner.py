"""Navigator original-video playback or live tablet-photo registration."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .native_person_dog import NativeMedia
from .video_timeline import VideoTimeline
from .person_dog_camera_scene import camera_scene,photo_input_rgb,PHOTO_CAPTURE_STEP


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--mode',choices=('video','photos','diagnostic'),required=True)
    parser.add_argument('--hdmi',action='store_true')
    parser.add_argument('--seconds',type=float,default=0,help='0 keeps running until interrupted')
    parser.add_argument('--output',type=Path,default=Path('/tmp/person_dog_two_result.json'))
    parser.add_argument('--preview',type=Path,help='lossless preview published by the single display owner')
    parser.add_argument('--verify-display',action='store_true',help='compare active isolated display buffer')
    args=parser.parse_args(argv)
    if args.seconds<0:parser.error('seconds must be nonnegative')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((args.root/'SHA256.json').read_text(encoding='utf-8'))
    for name,expected in manifest.items():
        if hashlib.sha256((args.root/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('package hash mismatch: '+name)
    media=NativeMedia(args.root/'libperson_dog.so')
    display=camera=None
    started=time.monotonic();records=[];last_saved=started
    last_preview=started-1
    last_capture=started;waiting_shown=False
    try:
        if args.hdmi:
            if args.mode in ('video','diagnostic'):
                from .fixed_scene_hdmi import NavigatorHDMI
                display=NavigatorHDMI()
            else:
                from .isolated_hdmi import NavigatorOverlay
                display=NavigatorOverlay()
        if args.mode=='diagnostic':
            frame=(args.root/'backgrounds/diagnostic.rgb').read_bytes()
            result=dict(mode='diagnostic',expected='four equal-width panels and undistorted circles')
            if display is not None:result['vdma_status']=display.show(frame)
            records.append(result)
            return
        if args.mode=='video':
            data=json.loads((args.root/'video/annotations.json').read_text(encoding='utf-8'))
            source=args.root/'video/source.mp4'
            if hashlib.sha256(source.read_bytes()).hexdigest()!=data['source_sha256']:
                raise ValueError('video differs from reviewed annotations')
            source=args.root/'video/playback.avi'
            timeline=VideoTimeline(data)
            media.open_video(source)
            video_backgrounds={position:(args.root/'backgrounds'/('video_'+position+'.rgb')).read_bytes()
                for position in ('person_left_of_dog','person_right_of_dog','same_horizontal_position')}
            background=(args.root/'backgrounds/unknown.rgb').read_bytes()
            loop_start=time.monotonic()
        else:
            entries=json.loads((args.root/'photos/gallery.json').read_text(encoding='utf-8'))['images']
            media.load_photos([args.root/'photos'/('scene%d.png'%i) for i in range(3)])
            from .stereo_live import StereoUIO
            matches=[p for p in Path('/sys/class/uio').glob('uio*')
                     if (p/'name').read_text().strip()=='z20-video-observer']
            if len(matches)!=1:raise ValueError('expected one camera observer UIO')
            camera=StereoUIO('/dev/'+matches[0].name,matches[0]/'maps',
                             independent_slots=True,sample_step=PHOTO_CAPTURE_STEP)
            background=(args.root/'backgrounds/unknown.rgb').read_bytes()
            if display is not None:display.show(background)
        while not args.seconds or time.monotonic()-started<args.seconds:
            if args.mode=='video':
                decoded=media.next_video()
                if decoded is None:
                    media.open_video(source);loop_start=time.monotonic();continue
                rgb,timestamp=decoded
                # Source timestamps select annotations even when hardware playback is slower.
                scene=timeline.at(timestamp)
                boxes=None if scene is None else [scene['boxes'][k] for k in ('person','dog')]
                if scene is not None:background=video_backgrounds[scene['position']]
                result=dict(input_source='decoded_video_file',decoder_input='video/playback.avi',
                            source_time_s=timestamp,scene=scene)
                wait=timestamp-(time.monotonic()-loop_start)
                if wait>0:time.sleep(min(wait,.2))
            else:
                snap=camera.latest()
                if snap is None:
                    if not waiting_shown and time.monotonic()-last_capture>1:
                        if display is not None:display.show((args.root/'backgrounds/unknown.rgb').read_bytes())
                        records.append(dict(input_source='actual_camera_pixels',scene=None,
                                             state='waiting_for_fresh_frame'))
                        records=records[-100:]
                        args.output.write_text(json.dumps(dict(mode=args.mode,results=records),
                                               ensure_ascii=False,indent=2),encoding='utf-8')
                        waiting_shown=True
                    time.sleep(.002);continue
                last_capture=time.monotonic();waiting_shown=False
                # The factory snapshot adapter exposes BGR; one half is the main view.
                rgb=photo_input_rgb(snap.pixels)
                result=camera_scene(rgb,media,entries,captured_ns=snap.captured_ns) if args.mode=='photos' else dict(
                    input_source='actual_camera_pixels',scene=None,display_boxes=None,
                    match=dict(scene_id=None),camera_depth_m=None)
                result.update(sequence=snap.sequence,captured_ns=snap.captured_ns)
                scene=result['scene'];boxes=result['display_boxes']
                index=result['match']['scene_id']
                background=(args.root/'backgrounds'/('unknown.rgb' if index is None
                             else 'photo%d.rgb'%index)).read_bytes()
            geometry=None if scene is None or scene['geometry'] is None else [
                scene['geometry'][k] for k in ('person_depth_m','dog_depth_m','distance_m')]
            frame=media.render(rgb,background,boxes,geometry)
            if display is not None:result['vdma_status']=display.show(frame.tobytes())
            if args.preview is not None and time.monotonic()-last_preview>=1:
                from .headless_preview import publish_frame
                equal=None
                if args.verify_display:
                    if display is None or not hasattr(display,'readback'):
                        raise ValueError('display readback requires the isolated overlay')
                    equal=display.readback()==frame.tobytes()
                    if not equal:raise RuntimeError('active display buffer differs from rendered preview')
                publish_frame(args.preview,frame,result=result,display_equal=equal)
                last_preview=time.monotonic()
            records.append(result);records=records[-100:]
            print(json.dumps(result,ensure_ascii=False),flush=True)
            if time.monotonic()-last_saved>1:
                args.output.write_text(json.dumps(dict(mode=args.mode,results=records),
                                       ensure_ascii=False,indent=2),encoding='utf-8')
                last_saved=time.monotonic()
    except KeyboardInterrupt:pass
    finally:
        if camera is not None:camera.close()
        if display is not None:display.close()
        media.close()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(dict(mode=args.mode,results=records),
                               ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
