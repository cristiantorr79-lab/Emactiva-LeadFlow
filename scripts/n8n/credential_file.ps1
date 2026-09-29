function Remove-LeadFlowCredentialFile {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
    }
}

function New-LeadFlowCredentialFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Remove-LeadFlowCredentialFile -Path $Path

    try {
        [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))

        if ($env:OS -eq 'Windows_NT') {
            $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            $account = [System.Security.Principal.NTAccount]::new($identity)
            $acl = [System.Security.AccessControl.FileSecurity]::new()
            $acl.SetOwner($account)
            $acl.SetAccessRuleProtection($true, $false)
            $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
                $identity,
                [System.Security.AccessControl.FileSystemRights]::FullControl,
                [System.Security.AccessControl.AccessControlType]::Allow
            )
            $acl.AddAccessRule($rule)
            Set-Acl -LiteralPath $Path -AclObject $acl -ErrorAction Stop
        }
    } catch {
        Remove-LeadFlowCredentialFile -Path $Path
        throw 'Could not create protected temporary credential file.'
    }
}
