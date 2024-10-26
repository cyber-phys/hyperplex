(require '[clj-http.lite.client :as client])
(require '[clojure.java.io :as io])
(require '[clojure.string :as str])
(require '[cheshire.core :as json])

(defn encode-file-to-base64 [file]
  (let [file-content (io/file file)]
    (java.util.Base64/encoder (slurp file-content "UTF-8"))))

(defn send-audio [file]
  (let [audio-data (encode-file-to-base64 file)
        response (client/post "https://api.replicate.com/v1/predictions"
                              {:headers {"Content-Type" "application/json"
                                         "Authorization" (str "Token " (System/getenv "REPLICATE_API_TOKEN"))}
                               :body (json/generate-string {"version" "b013d5113a06092349ebb9edf9d76d3303d278bb8e1460e3f03e1f9581dade18"
                                                            "input" {"filepath" audio-data
                                                                     "translate" false
                                                                     "return_timestamps" true}})})
        transcript (get-in response [:body :transcript])]
    {file transcript}))

(defn process-directory [dir]
  (let [files (file-seq (io/file dir))
        audio-files (filter #(str/ends-with? (.getName %) ".flac") files)
        transcripts (map send-audio audio-files)]
    (into {} transcripts)))

(defn convert-m4a-to-wav [dir]
  (let [files (file-seq (io/file dir))
        m4a-files (filter #(str/ends-with? (.getName %) ".m4a") files)]
    (doseq [file m4a-files]
      (let [wav-path (str/replace (.getAbsolutePath file) ".m4a" ".wav")]
        (.exec (Runtime/getRuntime) (str "ffmpeg -i " (.getAbsolutePath file) " " wav-path))))))

;; Note: Call the process-directory and convert-m4a-to-wav functions as needed.
