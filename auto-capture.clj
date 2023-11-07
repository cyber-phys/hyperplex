#!/usr/bin/env bb

(require '[babashka.process :refer [shell]])

;; Define the destination folder on the desktop
(def destination-folder (str (System/getProperty "user.home") "/Desktop/screencapture/"))

;; Create the directory if it does not exist
(shell "mkdir" "-p" destination-folder)

;; Function to take a screenshot and save it to the specified folder with the frame index
(defn capture-screenshot [index]
  (let [filename (format "frame-%05d.png" index)
        path (str destination-folder filename)]
    (shell "screencapture" path)))

;; Main loop to take screenshots every 30 seconds
(dotimes [i 1000]
  (capture-screenshot i)
  (Thread/sleep 5000)) ;; Sleep for 5000 milliseconds or 5 seconds
