#!/usr/bin/env bb

(require '[babashka.process :refer [shell]])
(import '(java.text SimpleDateFormat)
         '(java.util Date))

;; Define the destination folder on the desktop
(def destination-folder (str (System/getProperty "user.home") "/Desktop/screencapture/"))

;; Create the directory if it does not exist
(shell "mkdir" "-p" destination-folder)

;; Function to generate a timestamp string
(defn timestamp-str []
  (let [sdf (SimpleDateFormat. "yyyy-MM-dd_HH-mm-ss")]
    (.format sdf (Date.))))

;; Function to take a screenshot and save it to the specified folder with the frame index
(defn capture-screenshot []
  (let [filename (str (timestamp-str) ".png")
        path (str destination-folder filename)]
    (shell "screencapture" path)))

;; Main loop to take screenshots every 5 seconds
(dotimes [_ 1000]
  (capture-screenshot)
  (Thread/sleep 5000)) ;; Sleep for 5000 milliseconds or 5 seconds
