import cv2

def getTotal(videoPath):
    try:
        cap = cv2.VideoCapture(videoPath)
        totalFrames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
    except Exception as ex:
        print(ex)        
    return totalFrames




 