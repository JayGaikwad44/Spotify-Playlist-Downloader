import cv2
import numpy as np
import winsound  # For Windows beep sound (use 'os' for other platforms)

# Initialize the webcam (0 is the default camera)
cap = cv2.VideoCapture(0)

# Load the pre-trained Haar Cascade classifier for face detection
# This is a built-in classifier that comes with OpenCV
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# Flag to track if beep has been played (to play only once per detection session)
beep_played = False

print("Starting face detection... Press 'q' to quit")

while True:
    # Capture frame-by-frame from the webcam
    ret, frame = cap.read()
    
    # Check if frame was captured successfully
    if not ret:
        print("Failed to grab frame")
        break
    
    # Convert the frame to grayscale (face detection works better on grayscale images)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Detect faces in the frame
    # Parameters:
    # - scaleFactor: How much the image size is reduced at each scale
    # - minNeighbors: How many neighbors each candidate rectangle should have
    # - minSize: Minimum possible object size
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30)
    )
    
    # Process each detected face
    if len(faces) > 0:
        # Play beep sound once when face is first detected
        if not beep_played:
            # For Windows - plays a beep at 1000Hz for 200ms
            winsound.Beep(1000, 200)
            beep_played = True
            print("Face detected! Beep played.")
        
        # Draw rectangle and text for each face detected
        for (x, y, w, h) in faces:
            # Draw a green rectangle (bounding box) around the face
            # Parameters: image, top-left corner, bottom-right corner, color (BGR), thickness
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            
            # Prepare the text to display
            name = "Jay Gaikwad"
            
            # Calculate text size to position it properly above the face
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.9
            font_thickness = 2
            text_size = cv2.getTextSize(name, font, font_scale, font_thickness)[0]
            
            # Calculate position to center the text above the face
            text_x = x + (w - text_size[0]) // 2
            text_y = y - 10  # 10 pixels above the bounding box
            
            # Draw a black background rectangle for better text visibility
            cv2.rectangle(
                frame,
                (text_x - 5, text_y - text_size[1] - 5),
                (text_x + text_size[0] + 5, text_y + 5),
                (0, 0, 0),
                -1  # Filled rectangle
            )
            
            # Display the name above the face in white color
            cv2.putText(
                frame,
                name,
                (text_x, text_y),
                font,
                font_scale,
                (255, 255, 255),  # White color (BGR)
                font_thickness
            )
    else:
        # Reset beep flag when no face is detected
        # This allows beep to play again when face is re-detected
        beep_played = False
    
    # Display the number of faces detected in the top-left corner
    cv2.putText(
        frame,
        f"Faces detected: {len(faces)}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )
    
    # Display the resulting frame with annotations
    cv2.imshow('Face Detection - Press Q to Quit', frame)
    
    # Break the loop when 'q' key is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("Exiting...")
        break

# Release the webcam and close all OpenCV windows
cap.release()
cv2.destroyAllWindows()
print("Face detection stopped.")