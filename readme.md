# Legal Ontology

Note: We are using Lamda Stack on production/dev server

Setup Python Venv
```
python3 -m venv lambda-stack-with-tensorflow-pytorch --system-site-packages
```

Launch Server
```
source lambda-stack-with-tensorflow-pytorch/bin/activate
pnpm run dev
python server.py
sudo tailscale funnel --https 443 http://127.0.0.1:3000
sudo tailscale funnel --https 8443 http://127.0.0.1:8000
```