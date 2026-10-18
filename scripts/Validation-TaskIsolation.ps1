<# Test-only scheduler containment. Preserve enabled states without automatic runs. #>
function Disable-ValidationTaskTriggers($Service, [string]$FolderPath, [string]$ApplicationExe) {
    if ($FolderPath -notmatch '^\\OneDrivePCSync(?:Update)?Validation_[a-f0-9]{32}$') {
        throw 'Refusing to modify tasks outside a disposable validation folder'
    }
    $folder = $Service.GetFolder($FolderPath)
    foreach ($task in $folder.GetTasks(1)) {
        $definition = $task.Definition
        $enabled = $task.Enabled
        if ($definition.Actions.Count -ne 1 -or $definition.Actions.Item(1).Path -ine $ApplicationExe) {
            throw 'Validation task belongs to another application'
        }
        # Scheduler actions inherit the user's environment, not the fixture's
        # LOCALAPPDATA. Keep tasks on-demand only, including during long installs.
        $definition.Triggers.Clear()
        $registered = $folder.RegisterTaskDefinition(
            $task.Name, $definition, 4, $definition.Principal.UserId, $null, 3)
        if ($registered.Definition.Triggers.Count -ne 0) {
            throw 'Validation task retained an automatic trigger'
        }
        if ($registered.Enabled -ne $enabled) {
            throw 'Validation task isolation changed its enabled state'
        }
    }
}
