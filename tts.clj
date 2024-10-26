#!/usr/bin/env bb
(require '[babashka.process :refer [shell]])
(require '[cheshire.core :as json])
(require '[clojure.java.io :as io])
(require '[clj-http.lite.client :as client])
(import '(java.util Base64 UUID)
         '(java.nio.file Files Paths StandardOpenOption)
         '(java.nio ByteBuffer)
         '(java.text SimpleDateFormat)
         '(java.util Date))

(def openai-api-key (System/getenv "OPENAI_API_KEY"))
(def replicate-api-key (System/getenv "REPLICATE_API_TOKEN"))
(def elevenlabs-api-key (System/getenv "ELEVENLABS_API_KEY"))

(defn load-system-prompt [file-path]
  (let [file-contents (slurp file-path)]
    file-contents))

(defn speak [voice-id text-to-speak]
  (let [url (str "https://api.elevenlabs.io/v1/text-to-speech/" voice-id)
        headers {"Content-Type" "application/json"
                 "xi-api-key" elevenlabs-api-key}
        body (json/generate-string {
                                    "text" text-to-speak
                                    "voice_settings" {"similarity_boost" 0.5
                                                      "stability" 0.5
                                                      "style" 0.5
                                                      "use_speaker_boost" true}})
        response (client/post url {:headers headers :body body :as :byte-array :throw false})]
    ;; Return the byte array response
    (:body response)))

(defn write-binary [binary-data file-name]
  (let [output-stream (java.io.FileOutputStream. file-name)]
    (.write output-stream binary-data)
    (.close output-stream)))

;; Function to post base64 image frame to OpenAI API and return the response body
(defn oai-image-description [frame]
  (let [response (client/post "https://api.openai.com/v1/chat/completions"
                              {:headers {"Content-Type" "application/json"
                                         "Authorization" (str "Bearer " openai-api-key)}
                               :body (json/generate-string {:model "gpt-4-vision-preview"
                                                            :messages [{:role "user"
                                                                        :content [{:type "text"
                                                                                   :text "What’s in this image?"}
                                                                                  {:type "image_url"
                                                                                   :image_url {:url (str "data:image/jpeg;base64," frame)}}]}]
                                                            :max_tokens 300})
                               :throw false})]
    (let [response-body (:body response)]
      (println "Response body:" response-body)
      response-body)))

(defn strip-chars [s]
  (subs s 7 (- (count s) 3)))

(defn oai-text-prompt [system-prompt user-input]
  (let [response (client/post "https://api.openai.com/v1/chat/completions"
                              {:headers {"Content-Type" "application/json"
                                         "Authorization" (str "Bearer " openai-api-key)}
                               :body (json/generate-string {:model "gpt-4-1106-preview"
                                                            :messages [{:role "system"
                                                                        :content system-prompt}
                                                                       {:role "user"
                                                                        :content user-input}]
                                                            :max_tokens 4000})
                              :throw false})]
    (let [response-body (json/parse-string (:body response) true)
          content (:content (:message (nth (:choices response-body) 0)))]
      (println "Response content:" (strip-chars content))
      (strip-chars content))))

;; Function to post to nougat hosted on replicate
(defn ocr-pdf-post [pdf-url]
  (let [response (client/post "https://api.replicate.com/v1/deployments/chartierluc/nougat/predictions"
                              {:headers {"Content-Type" "application/json"
                                         "Authorization" (str "Token " replicate-api-key)}
                               :body (json/generate-string {"version" "fbf959aabb306f7cc83e31da4a5ee0ee78406d11216295dbd9ef75aba9b30538"
                                                         "input" {"document" (str pdf-url)
                                                                  "postprocess" false
                                                                  "early_stopping" false}})
                               :throw false})]
    (let [response-body (json/parse-string (:body response) true)
          get-url (:get (:urls response-body))]
      (println "GET URL:" get-url)
      get-url)))

(defn ocr-pdf-get [prediction-url]
  (let [response (client/get prediction-url {:headers {"Authorization" (str "Token " replicate-api-key)}})
        response-body (json/parse-string (:body response) true)] ;; Parse the response body
    ;; Print or process the response body as needed
    ;;(println "Response Body:" response-body)
    response-body)) ;; Return the full response body or a reduced form

(defn ocr-pdf-poll [prediction-url]
  (Thread/sleep 2000) ;; Initial wait for 2 seconds
  (loop []
    (let [response (ocr-pdf-get prediction-url)
          body (json/parse-string (:body response) true)
          status (:status response)]
      (println "Current Status:" status)
      (cond
        (= status "succeeded") (:output response) ;; Return the output URL when status is 'succeeded'
        (= status "error") (throw (Exception. "Error in processing"))
        :else (do (Thread/sleep 1000) ;; Poll every second
                  (recur))))))

(defn fetch-url-contents [url]
  (let [response (client/get url)
        contents (:body response)]
    (println "Fetched Content:" (strip-chars contents))
    (strip-chars contents)))

;; Define the destination folder on the desktop
(def destination-folder (str (System/getProperty "user.home") "/Desktop/audio/"))

;; Create the directory if it does not exist
(shell "mkdir" "-p" destination-folder)

;; Function to generate a timestamp string in ISO 8601 format
(defn timestamp-iso-str []
  (let [sdf (SimpleDateFormat. "yyyy-MM-dd'T'HH:mm:ss'Z'")]
    (.format sdf (Date.))))

;; Function to generate a UUID v4 string
(defn uuid-v4 []
  (.toString (UUID/randomUUID)))


;; Function to convert image to base64
(defn image-to-base64 [path]
  (try
    (let [file-path (Paths/get path (make-array String 0))]
      (let [file-content (Files/readAllBytes file-path)]
        (.encodeToString (Base64/getEncoder) file-content)))
    (catch Exception e
      (println "Error converting image to Base64:" (.getMessage e))
      nil))) ;; Return nil to indicate failure

(defn split-into-chunks [s]
  (let [words (clojure.string/split s #"\s")
        chunks (atom [[]])
        add-word (fn [word]
                   (let [current-chunk (last @chunks)]
                     (if (<= (+ (apply + (map count current-chunk)) (count word)) 2000)
                       (swap! chunks update (dec (count @chunks)) conj word)
                       (swap! chunks conj [word]))))]
    (doseq [word words] (add-word word))
    (map clojure.string/join @chunks)))

(defn process-chunks [chunks]
  (doseq [[chunk-number chunk] (map-indexed vector chunks)]
    (write-binary (speak "D38z5RcWu1voky8WS1ja" chunk) (str "tts-" (inc chunk-number) ".mp3"))))

(defn process-string [s]
  (-> s
      split-into-chunks
      process-chunks))

(defn -main [& args]
  (let [pdf-url (first args)]
    (if pdf-url
      (do
        (println "Processing PDF URL:" pdf-url)
        (process-string (fetch-url-contents (ocr-pdf-poll (ocr-pdf-post pdf-url))))
        ;(write-binary (speak "D38z5RcWu1voky8WS1ja" (str (fetch-url-contents (ocr-pdf-poll (ocr-pdf-post pdf-url))))) "tts.mp3" )
       ;(write-binary (speak "D38z5RcWu1voky8WS1ja" "testing testing 123") "tts.mp3" )
        (println "Processing complete."))
      (println "No PDF URL provided."))))

(when (not (:gen-class *ns*))
  (apply -main *command-line-args*))
