#!/usr/bin/env bb

(require '[babashka.process :refer [shell]])
(require '[cheshire.core :as json])
(require '[clojure.java.io :as io])
(require '[clj-http.lite.client :as client])
(import '(java.util Base64 UUID)
         '(java.nio.file Files Paths)
         '(java.text SimpleDateFormat)
         '(java.util Date))

(def openai-api-key (System/getenv "OPENAI_API_KEY"))
(def replicate-api-key (System/getenv "REPLICATE_API_TOKEN"))

(defn load-system-prompt [file-path]
  (let [file-contents (slurp file-path)]
    file-contents))

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
      (println "Response content:" content)
      content)))

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
(def destination-folder (str (System/getProperty "user.home") "/Desktop/hypergraph/"))

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

;; Function to save a JSON hypergraph to a file
(defn save-json-hypergraph [json-object path]
  (with-open [writer (io/writer path)]
    (.write writer (json/generate-string json-object))
    (.flush writer)))

;; Function to save screenshot
(defn capture-screenshot []
  (let [temp-file (str "/tmp/" (uuid-v4) ".png")]
    (println "Capturing screenshot to:" temp-file)
    (shell "screencapture" "-x" temp-file)
    (try
      (let [file (io/file temp-file)]
        (when (.exists file)
          (println "Screenshot saved to:" (.getAbsolutePath file))
          (let [base64 (image-to-base64 temp-file)]
  ;;          (println "Base64 string:" base64) ;; This will print the Base64 string
            base64)))
      (catch Exception e
        (println "Error capturing screenshot:" (.getMessage e)))
      (finally
        (println "Deleting temporary file:" temp-file)
        (shell "rm" "-f" temp-file)))))

(defn update-hypergraph [base64-image]
  (when (nil? base64-image)
    (println "No image data to update.")) ;; Check for nil Base64 string
  (let [hypergraph-path (str destination-folder "hypergraph.json")
        hypergraph (if (.exists (io/file hypergraph-path))
                     (json/parse-string (slurp hypergraph-path) true)
                     {:nodes [] :hyperedges []})
        node {:id (uuid-v4) :type "screenshot" :data base64-image :time (timestamp-iso-str) :description (oai-image-description base64-image)}
        updated-hypergraph (update hypergraph :nodes conj node)]
;;    (println "Saving updated hypergraph:" updated-hypergraph) ;; Debugging line
    (save-json-hypergraph updated-hypergraph hypergraph-path)))

(oai-text-prompt (load-system-prompt "./olog-prompt.md") (fetch-url-contents (ocr-pdf-poll (ocr-pdf-post (str "https://arxiv.org/pdf/1912.02258.pdf")))))