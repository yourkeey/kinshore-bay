# First run saves the token in bot/.env; later runs start without asking again.
$ErrorActionPreference = 'Stop'
$envFile = Join-Path $PSScriptRoot '.env'
$currentToken = [Environment]::GetEnvironmentVariable('BOT_TOKEN', 'Process')
if ([string]::IsNullOrWhiteSpace($currentToken) -and -not (Test-Path -LiteralPath $envFile)) {
    Write-Host 'First launch: the token will be saved locally in bot/.env.'
    $secureToken = Read-Host 'BotFather token (input is hidden)' -AsSecureString
    $tokenPointer = [IntPtr]::Zero
    $writer = $null
    try {
        $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
        $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer).Trim()
        if ($plainToken -notmatch '^[0-9]+:[A-Za-z0-9_-]+$') { throw 'Invalid token format. No file was saved.' }
        $stream = [System.IO.File]::Open($envFile, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        $writer.WriteLine('BOT_TOKEN=' + $plainToken)
    } finally {
        if ($null -ne $writer) { $writer.Dispose() }
        $plainToken = $null
        if ($tokenPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer) }
        $secureToken.Dispose()
    }
    Write-Host 'Token saved. Starting the bot...'
}
& python (Join-Path $PSScriptRoot 'bot.py')
exit $LASTEXITCODE
