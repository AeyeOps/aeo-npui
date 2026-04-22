param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("open-tab", "send-text", "send-key", "capture-screen", "close-tab", "metadata")]
    [string]$Action,
    [string]$Title,
    [string]$CommandLine,
    [string]$OutputPath,
    [string]$Text,
    [string]$Keys,
    [string]$StartingDirectory = "C:\dev\npu",
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"

function Get-WindowsTerminalWindow {
    Get-Process WindowsTerminal -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -ne "" } |
        Select-Object -First 1
}

function Wait-WindowTitle {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TitleText,
        [int]$Timeout = 30
    )

    $shell = New-Object -ComObject WScript.Shell
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        if ($shell.AppActivate($TitleText)) {
            Start-Sleep -Milliseconds 150
            return $true
        }
        Start-Sleep -Milliseconds 200
    }
    return $false
}

function Convert-ToSendKeysLiteral {
    param([string]$Value)

    $builder = [System.Text.StringBuilder]::new()
    foreach ($char in $Value.ToCharArray()) {
        switch ($char) {
            '+' { [void]$builder.Append('{+}') }
            '^' { [void]$builder.Append('{^}') }
            '%' { [void]$builder.Append('{%}') }
            '~' { [void]$builder.Append('{~}') }
            '(' { [void]$builder.Append('{(}') }
            ')' { [void]$builder.Append('{)}') }
            '[' { [void]$builder.Append('{[}') }
            ']' { [void]$builder.Append('{]}') }
            '{' { [void]$builder.Append('{{}') }
            '}' { [void]$builder.Append('{}}') }
            default { [void]$builder.Append($char) }
        }
    }
    $builder.ToString()
}

function Capture-Screen {
    param([string]$Path)

    if (-not $Path) {
        throw "capture-screen requires -OutputPath"
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()
    return @{
        logical_width = $bounds.Width
        logical_height = $bounds.Height
        output_path = $Path
    }
}

switch ($Action) {
    "open-tab" {
        if (-not $Title) {
            throw "open-tab requires -Title"
        }
        $launch = 'wt.exe -w 0 nt --title "{0}" --suppressApplicationTitle -d "{1}" pwsh.exe -NoLogo -NoProfile' -f $Title, $StartingDirectory
        Start-Process cmd.exe -WorkingDirectory "C:\" -ArgumentList @("/c", $launch) | Out-Null
        $activated = Wait-WindowTitle -TitleText $Title -Timeout $TimeoutSeconds
        if (-not $activated) {
            throw "Timed out waiting for Windows Terminal tab title '$Title'"
        }
        @{ title = $Title; activated = $activated } | ConvertTo-Json -Compress
        break
    }
    "send-text" {
        if (-not $Title) {
            throw "send-text requires -Title"
        }
        if ($null -eq $Text) {
            throw "send-text requires -Text"
        }
        if (-not (Wait-WindowTitle -TitleText $Title -Timeout $TimeoutSeconds)) {
            throw "Timed out focusing '$Title'"
        }
        $shell = New-Object -ComObject WScript.Shell
        $shell.SendKeys((Convert-ToSendKeysLiteral -Value $Text))
        @{ title = $Title; text = $Text } | ConvertTo-Json -Compress
        break
    }
    "send-key" {
        if (-not $Title) {
            throw "send-key requires -Title"
        }
        if (-not $Keys) {
            throw "send-key requires -Keys"
        }
        if (-not (Wait-WindowTitle -TitleText $Title -Timeout $TimeoutSeconds)) {
            throw "Timed out focusing '$Title'"
        }
        $shell = New-Object -ComObject WScript.Shell
        $shell.SendKeys($Keys)
        @{ title = $Title; keys = $Keys } | ConvertTo-Json -Compress
        break
    }
    "capture-screen" {
        Capture-Screen -Path $OutputPath | ConvertTo-Json -Compress
        break
    }
    "close-tab" {
        if (-not $Title) {
            throw "close-tab requires -Title"
        }
        if (-not (Wait-WindowTitle -TitleText $Title -Timeout $TimeoutSeconds)) {
            throw "Timed out focusing '$Title'"
        }
        $shell = New-Object -ComObject WScript.Shell
        $shell.SendKeys("^+w")
        @{ title = $Title; closed = $true } | ConvertTo-Json -Compress
        break
    }
    "metadata" {
        Add-Type -AssemblyName System.Windows.Forms
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $window = Get-WindowsTerminalWindow
        @{
            logical_width = $bounds.Width
            logical_height = $bounds.Height
            terminal_window_title = if ($window) { $window.MainWindowTitle } else { $null }
            terminal_process_id = if ($window) { $window.Id } else { $null }
        } | ConvertTo-Json -Compress
        break
    }
}
