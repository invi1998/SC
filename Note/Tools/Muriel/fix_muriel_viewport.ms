/* Select the imported character mesh(es), then run this script in 3ds Max.
   Material assignments are undoable. No scene save or FBX export is performed.
   Real active-viewport PNGs are saved before and after the assignment.
*/
(
    local scriptDir = getFilenamePath (getSourceFileName())
    local captureDir = (dotNetClass "System.IO.Path").GetFullPath (scriptDir + "../../Images/BlinkEffects/Muriel_Max_Captures/")
    makeDir captureDir all:true
    local runId = (timeStamp()) as string
    local prefix = captureDir + "/" + runId
    local targets = for obj in selection where
        ((isKindOf obj.baseObject Editable_Mesh) or (isKindOf obj.baseObject Editable_Poly)) collect obj

    fn captureViewport filename =
    (
        completeRedraw()
        local picture = gw.getViewportDib()
        picture.filename = filename
        local saved = save picture
        close picture
        if not saved do throw ("Could not save viewport: " + filename)
    )

    fn grayCopy original =
    (
        if original != undefined and (classOf original == MultiMaterial) then
        (
            local result = copy original
            for i = 1 to (getNumSubMtls original) do
                setSubMtl result i (grayCopy (getSubMtl original i))
            result
        )
        else
        (
            local label = if original == undefined then "Muriel_UV_Gray" else original.name
            local result = standardMaterial name:label diffuse:(color 180 180 180)
            result.specularLevel = 0
            result.opacity = 100
            -- Normalize opaque surfaces even if FBX imported contradictory alpha.
            if original != undefined and (isProperty original #opacity) and
                ((matchPattern label pattern:"*TearLine*") or (matchPattern label pattern:"*EyeLashes*")) do
                result.opacity = original.opacity
            result
        )
    )

    if targets.count == 0 then
        messageBox "Select the imported character mesh (Editable Mesh/Poly), then run again. Bones are skipped." title:"Muriel viewport repair"
    else
    (
        captureViewport (prefix + "_before.png")
        local report = createFile (prefix + "_process.txt")
        format "Started: %\nMeshes: %\n" (localTime) targets.count to:report
        try
        (
            undo "Muriel gray viewport materials" on
            (
                for obj in targets do
                (
                    format "Mesh: % | previous material: %\n" obj.name obj.material to:report
                    obj.material = grayCopy obj.material
                )
            )
            captureViewport (prefix + "_after.png")
            local noteDir = (dotNetClass "System.IO.Path").GetFullPath (scriptDir + "../../")
            local noteFiles = getFiles (noteDir + "/3_*.md")
            if noteFiles.count == 1 then
            (
                local relativeDir = "./Images/BlinkEffects/Muriel_Max_Captures/" + runId
                local snippet = "\n\n### Max viewport capture / " + runId + "\n\n"
                snippet += "Captured by fix_muriel_viewport.ms in 3ds Max. Gray material assignment; visual review still required.\n\n"
                snippet += "![Max viewport before assignment](" + relativeDir + "_before.png)\n\n"
                snippet += "![Max viewport after assignment](" + relativeDir + "_after.png)\n"
                (dotNetClass "System.IO.File").AppendAllText noteFiles[1] snippet ((dotNetClass "System.Text.Encoding").UTF8)
                format "Screenshots appended to: %\n" noteFiles[1] to:report
            )
            else format "Document append skipped: expected one 3_*.md file.\n" to:report
            format "Finished: %\nBefore: %_before.png\nAfter: %_after.png\n" (localTime) prefix prefix to:report
            close report
            messageBox ("Gray materials assigned. Ctrl+Z undoes assignments.\nScreenshots and process log:\n" + captureDir + "\n\nIf still dark, enable Default Lights in the viewport.") title:"Muriel viewport repair"
        )
        catch
        (
            format "ERROR: %\n" (getCurrentException()) to:report
            close report
            messageBox ((getCurrentException()) as string) title:"Muriel viewport repair error"
        )
    )
)
