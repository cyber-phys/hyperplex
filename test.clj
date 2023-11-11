(require '[babashka.curl :as curl])
(require '[cheshire.core :as json])

(def openai-api-key "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") ; replace with your actual OpenAI API key

(defn post-chat-completion [image-url]
  (curl/post "https://api.openai.com/v1/chat/completions"
             {:headers {"Content-Type" "application/json"
                        "Authorization" (str "Bearer " openai-api-key)}
:body (json/generate-string {
        :model "gpt-4-vision-preview"
        :messages [{:role "user"
                    :content [{:type "text"
                               :text "What’s in this image?"}
                              {:type "image_url"
                               :image_url {:url image-url}}]}]
        :max_tokens 300})

              :throw false}))

(defn main []
  (let [response (post-chat-completion "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg")
        body (json/parse-string (:body response) true)]
    (println "Response:" (:body response))
    (if-let [error (:error body)]
      (println "Error:" error)
      (println "Output:" (:choices body)))))

(main)

