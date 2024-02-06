import cv2

def get_total_frames(videoPath):
    try:
        cap = cv2.VideoCapture(videoPath)
        totalFrames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
    except Exception as ex:
        print(ex)        
    return totalFrames

def export_frame_at_distance(video_path:str,video_data:list,distance_rate)->None:
    cap = cv2.VideoCapture(video_path)
    pass




 