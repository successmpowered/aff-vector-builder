# Static file server + CORS proxy for explorer/
# Proxy routes:
#   /proxy/koios/*  → https://koios.vector.testnet.apexfusion.org/api/v1/*
#   /proxy/ogmios   → https://ogmios.vector.testnet.apexfusion.org
param([int]$Port = 0)
if ($Port -eq 0) {
    $Port = if ($env:PORT) { [int]$env:PORT } else { 5500 }
}

$root = $PSScriptRoot
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
Write-Host "Explorer running at http://localhost:$Port/"
Write-Host "Proxying Koios → https://koios.vector.testnet.apexfusion.org/api/v1"
Write-Host "Proxying Ogmios → https://ogmios.vector.testnet.apexfusion.org"

function Proxy-Request($req, $res, $targetUrl) {
    try {
        $webReq = [System.Net.HttpWebRequest]::Create($targetUrl)
        $webReq.Method = $req.HttpMethod
        $webReq.Accept = "application/json"
        $webReq.UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        $webReq.Timeout = 10000
        # Suppress certificate validation issues if any
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

        if ($req.HttpMethod -eq "POST") {
            $webReq.ContentType = "application/json"
            if ($req.ContentLength64 -gt 0) {
                $body = New-Object byte[] $req.ContentLength64
                [void]$req.InputStream.Read($body, 0, $body.Length)
                $webReq.ContentLength = $body.Length
                $upStream = $webReq.GetRequestStream()
                $upStream.Write($body, 0, $body.Length)
                $upStream.Close()
            } else {
                $webReq.ContentLength = 0
            }
        }

        $webResp = $webReq.GetResponse()
        $reader  = New-Object System.IO.StreamReader($webResp.GetResponseStream())
        $content = $reader.ReadToEnd()
        $reader.Close()

        $bytes = [System.Text.Encoding]::UTF8.GetBytes($content)
        $res.ContentType = "application/json; charset=utf-8"
        $res.Headers.Add("Access-Control-Allow-Origin", "*")
        $res.OutputStream.Write($bytes, 0, $bytes.Length)

    } catch [System.Net.WebException] {
        $errResp = $_.Exception.Response
        $statusCode = if ($errResp) { [int]$errResp.StatusCode } else { 502 }
        $errBody = ""
        if ($errResp) {
            try {
                $errReader = New-Object System.IO.StreamReader($errResp.GetResponseStream())
                $errBody = $errReader.ReadToEnd()
                $errReader.Close()
            } catch {}
        }
        $errMsg = if ($errBody) { $errBody } else { '{"error":"proxy error: ' + $_.Exception.Message + '"}' }
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($errMsg)
        $res.StatusCode = $statusCode
        $res.ContentType = "application/json"
        $res.OutputStream.Write($bytes, 0, $bytes.Length)

    } catch {
        $errMsg = [System.Text.Encoding]::UTF8.GetBytes('{"error":"' + $_.Exception.Message + '"}')
        $res.StatusCode = 502
        $res.ContentType = "application/json"
        $res.OutputStream.Write($errMsg, 0, $errMsg.Length)
    }
}

function Serve-File($req, $res) {
    $path = $req.Url.LocalPath.TrimStart('/')
    if ($path -eq '') { $path = 'index.html' }
    $file = Join-Path $root $path

    if (Test-Path $file -PathType Leaf) {
        $ext = [System.IO.Path]::GetExtension($file).ToLower()
        $mime = switch ($ext) {
            '.html' { 'text/html; charset=utf-8' }
            '.js'   { 'application/javascript' }
            '.css'  { 'text/css' }
            '.json' { 'application/json' }
            default { 'application/octet-stream' }
        }
        $bytes = [System.IO.File]::ReadAllBytes($file)
        $res.ContentType = $mime
        $res.OutputStream.Write($bytes, 0, $bytes.Length)
    } else {
        $msg = [System.Text.Encoding]::UTF8.GetBytes("Not found: $path")
        $res.StatusCode = 404
        $res.OutputStream.Write($msg, 0, $msg.Length)
    }
}

try {
    while ($listener.IsListening) {
        $ctx = $listener.GetContext()
        $req = $ctx.Request
        $res = $ctx.Response

        # CORS preflight
        if ($req.HttpMethod -eq "OPTIONS") {
            $res.Headers.Add("Access-Control-Allow-Origin", "*")
            $res.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            $res.Headers.Add("Access-Control-Allow-Headers", "Content-Type, Accept")
            $res.StatusCode = 204
            $res.OutputStream.Close()
            continue
        }

        $localPath = $req.Url.LocalPath

        if ($localPath -like '/proxy/koios*') {
            $apiPath = $localPath -replace '^/proxy/koios', ''
            $query   = if ($req.Url.Query) { $req.Url.Query } else { '' }
            $target  = "https://koios.vector.testnet.apexfusion.org/api/v1$apiPath$query"
            Write-Host "$($req.HttpMethod) $localPath → $target"
            Proxy-Request $req $res $target

        } elseif ($localPath -like '/proxy/ogmios*') {
            $target = "https://ogmios.vector.testnet.apexfusion.org"
            Write-Host "$($req.HttpMethod) $localPath → $target"
            Proxy-Request $req $res $target

        } else {
            Serve-File $req $res
        }

        $res.OutputStream.Close()
    }
} finally {
    $listener.Stop()
}
