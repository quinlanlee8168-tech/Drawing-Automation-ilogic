' iLogic Rule: Export drawing PDFs for top assembly + all BOM children in Structured order
' Author: ChatGPT
'
' What this rule does:
' 1) Starts from the currently active Assembly (.iam)
' 2) Walks Structured BOM recursively (parent assemblies + child subassemblies + parts)
' 3) Finds the newest matching drawing file for each item (<ModelName>.idw or <ModelName>.dwg)
' 4) Exports each drawing to PDF in BOM order
'
' Notes:
' - Inventor's built-in PDF translator exports one drawing at a time.
' - This rule creates an ordered PDF set in one folder.
' - If you need one final combined PDF, merge the exported PDFs afterward.

Imports IOPath = System.IO.Path
Imports IOFile = System.IO.File
Imports IODirectory = System.IO.Directory
Imports System.Collections.Generic
Imports System.Text.RegularExpressions

Sub Main()
    Dim asmDoc As AssemblyDocument = TryCast(ThisApplication.ActiveDocument, AssemblyDocument)
    If asmDoc Is Nothing Then
        MessageBox.Show("Open the top-level assembly (.iam) before running this rule.", "iLogic")
        Return
    End If

    Dim projectRoot As String = IOPath.GetDirectoryName(asmDoc.FullFileName)

    ' Optional prompt: user can enter one or more drawing folders at runtime.
    ' Separate multiple folders with semicolons (;). Leave blank to use assembly folder.
    Dim drawingsRootInput As String = InputBox(
        "Enter drawing folder path(s), separated by semicolons (;)." & vbCrLf &
        "Leave blank to use the assembly folder:",
        "Drawing Search Folders",
        projectRoot
    )
    Dim drawingsRootOverrides As List(Of String) = ParseDrawingRootsInput(drawingsRootInput)

    Dim outputFolder As String = IOPath.Combine(projectRoot, "PDF_OUTPUT")
    If Not IODirectory.Exists(outputFolder) Then
        IODirectory.CreateDirectory(outputFolder)
    End If

    ' Build a drawing index once from the selected drawing folders.
    ' If duplicate exact-name drawings are found, the newest modified file is kept.
    Dim drawingIndex As New Dictionary(Of String, String)(StringComparer.OrdinalIgnoreCase)
    Dim drawingSearchRoots As List(Of String) = ResolveDrawingSearchRoots(projectRoot, drawingsRootOverrides)
    BuildDrawingIndex(drawingSearchRoots, drawingIndex)

    Dim orderedModelPaths As New List(Of String)
    Dim orderedPartNumbers As New List(Of String)
    Dim orderedQuantities As New List(Of Integer)
    Dim orderedFinishes As New List(Of String)
    Dim orderedMaterials As New List(Of String)
    Dim orderedRevisions As New List(Of String)
    CollectBomModelPaths(asmDoc, orderedModelPaths, orderedPartNumbers, orderedQuantities, orderedFinishes, orderedMaterials, orderedRevisions)

    Dim exportCount As Integer = 0
    Dim missingDrawings As New List(Of String)
    Dim manifestLines As New List(Of String)
    manifestLines.Add("Order,RAW PART NUMBER,PART_NUMBER_FILTER,Revision,ModelPath,DrawingPath,ExportedPdf,Quantity,Finish,Material,Status")
    Dim sequence As Integer = 1

    ' Preserve repeated occurrences from BOM (do not de-duplicate by model path).
    For i As Integer = 0 To orderedModelPaths.Count - 1
        Dim modelPath As String = orderedModelPaths(i)
        Dim partNumber As String = ""
        If i < orderedPartNumbers.Count Then
            partNumber = orderedPartNumbers(i)
        End If
        Dim finish As String = ""
        If i < orderedFinishes.Count Then
            finish = orderedFinishes(i)
        End If
        Dim material As String = ""
        If i < orderedMaterials.Count Then
            material = orderedMaterials(i)
        End If
        Dim revision As String = ""
        If i < orderedRevisions.Count Then
            revision = orderedRevisions(i)
        End If
        Dim quantity As Integer = 1
        If i < orderedQuantities.Count Then
            quantity = orderedQuantities(i)
        End If
        If quantity < 1 Then
            quantity = 1
        End If
        Dim filteredPartNumber As String = FilterPartNumber(partNumber)

        Dim orderedPrefix As String = sequence.ToString("D4")
        Dim drawingPath As String = FindDrawingForModel(modelPath, drawingIndex)
        If String.IsNullOrEmpty(drawingPath) Then
            missingDrawings.Add(modelPath)
            manifestLines.Add(
                CsvEscape(orderedPrefix) & "," &
                CsvEscape(partNumber) & "," &
                CsvEscape(filteredPartNumber) & "," &
                CsvEscape(revision) & "," &
                CsvEscape(modelPath) & "," &
                CsvEscape("") & "," &
                CsvEscape("") & "," &
                CsvEscape(quantity.ToString()) & "," &
                CsvEscape(finish) & "," &
                CsvEscape(material) & "," &
                CsvEscape("MissingDrawing")
            )
            sequence += 1
            Continue For
        End If

        Dim pdfName As String = orderedPrefix & "_" & IOPath.GetFileNameWithoutExtension(modelPath) & ".pdf"
        Dim pdfPath As String = IOPath.Combine(outputFolder, pdfName)

        If ExportDrawingToPdf(drawingPath, pdfPath) Then
            exportCount += 1
            manifestLines.Add(
                CsvEscape(orderedPrefix) & "," &
                CsvEscape(partNumber) & "," &
                CsvEscape(filteredPartNumber) & "," &
                CsvEscape(revision) & "," &
                CsvEscape(modelPath) & "," &
                CsvEscape(drawingPath) & "," &
                CsvEscape(pdfPath) & "," &
                CsvEscape(quantity.ToString()) & "," &
                CsvEscape(finish) & "," &
                CsvEscape(material) & "," &
                CsvEscape("Exported")
            )
        Else
            manifestLines.Add(
                CsvEscape(orderedPrefix) & "," &
                CsvEscape(partNumber) & "," &
                CsvEscape(filteredPartNumber) & "," &
                CsvEscape(revision) & "," &
                CsvEscape(modelPath) & "," &
                CsvEscape(drawingPath) & "," &
                CsvEscape("") & "," &
                CsvEscape(quantity.ToString()) & "," &
                CsvEscape(finish) & "," &
                CsvEscape(material) & "," &
                CsvEscape("ExportFailed")
            )
        End If
        sequence += 1
    Next

    Dim tempManifestCsvPath As String = IOPath.Combine(outputFolder, "PDF_BOM_ORDER.csv")
    Dim manifestPath As String = IOPath.Combine(outputFolder, "PDF_BOM_ORDER.xlsx")
    IOFile.WriteAllLines(tempManifestCsvPath, manifestLines.ToArray())
    Dim highlightedManifestPath As String = CreateHighlightedManifestWorkbook(tempManifestCsvPath, manifestPath)
    If IOFile.Exists(tempManifestCsvPath) Then
        IOFile.Delete(tempManifestCsvPath)
    End If

    Dim reportPath As String = IOPath.Combine(outputFolder, "missing_drawings.txt")
    IOFile.WriteAllLines(reportPath, missingDrawings.ToArray())

    MessageBox.Show(
        "Export complete." & vbCrLf &
        "PDFs exported: " & exportCount.ToString() & vbCrLf &
        "Missing drawings: " & missingDrawings.Count.ToString() & vbCrLf &
        "Order manifest: " & highlightedManifestPath & vbCrLf &
        "Output folder: " & outputFolder,
        "iLogic"
    )
End Sub

Sub CollectBomModelPaths(asmDoc As AssemblyDocument, orderedModelPaths As List(Of String), orderedPartNumbers As List(Of String), orderedQuantities As List(Of Integer), orderedFinishes As List(Of String), orderedMaterials As List(Of String), orderedRevisions As List(Of String))
    ' Include top-level assembly first
    orderedModelPaths.Add(asmDoc.FullFileName)
    orderedPartNumbers.Add(GetPartNumberFromDocument(asmDoc))
    orderedQuantities.Add(1)
    orderedFinishes.Add(GetCustomPropertyValue(asmDoc, "Finish"))
    orderedMaterials.Add(GetCustomPropertyValue(asmDoc, "Material"))
    orderedRevisions.Add(GetRevisionFromDocument(asmDoc))

    Dim bom As BOM = asmDoc.ComponentDefinition.BOM
    bom.StructuredViewEnabled = True
    bom.StructuredViewFirstLevelOnly = False

    Dim structured As BOMView = bom.BOMViews.Item("Structured")

    For Each row As BOMRow In structured.BOMRows
        AddBomRowRecursive(row, orderedModelPaths, orderedPartNumbers, orderedQuantities, orderedFinishes, orderedMaterials, orderedRevisions, 1)
    Next
End Sub

Sub AddBomRowRecursive(row As BOMRow, orderedModelPaths As List(Of String), orderedPartNumbers As List(Of String), orderedQuantities As List(Of Integer), orderedFinishes As List(Of String), orderedMaterials As List(Of String), orderedRevisions As List(Of String), parentMultiplier As Integer)
    Dim rowQty As Integer = GetBomRowQuantity(row)
    Dim effectiveQty As Integer = rowQty * Math.Max(1, parentMultiplier)
    If effectiveQty < 1 Then
        effectiveQty = 1
    End If

    Try
        Dim compDef As ComponentDefinition = row.ComponentDefinitions.Item(1)
        Dim doc As Document = compDef.Document

        If Not String.IsNullOrEmpty(doc.FullFileName) Then
            orderedModelPaths.Add(doc.FullFileName)
            orderedPartNumbers.Add(GetPartNumberFromDocument(doc))
            orderedQuantities.Add(effectiveQty)
            orderedFinishes.Add(GetCustomPropertyValue(doc, "Finish"))
            orderedMaterials.Add(GetCustomPropertyValue(doc, "Material"))
            orderedRevisions.Add(GetRevisionFromDocument(doc))
        End If
    Catch
        ' Some rows may not resolve cleanly; skip safely.
    End Try

    If row.ChildRows Is Nothing Then
        Return
    End If

    For Each child As BOMRow In row.ChildRows
        AddBomRowRecursive(child, orderedModelPaths, orderedPartNumbers, orderedQuantities, orderedFinishes, orderedMaterials, orderedRevisions, effectiveQty)
    Next
End Sub

Function GetBomRowQuantity(row As BOMRow) As Integer
    If row Is Nothing Then
        Return 1
    End If

    Try
        Dim q As Double = CDbl(row.ItemQuantity)
        Dim rounded As Integer = CInt(Math.Round(q))
        If rounded > 0 Then
            Return rounded
        End If
    Catch
    End Try

    Return 1
End Function

Function GetPartNumberFromDocument(doc As Document) As String
    Try
        Dim designTracking As PropertySet = doc.PropertySets.Item("Design Tracking Properties")
        Dim partNumberProp As Inventor.Property = designTracking.Item("Part Number")
        If partNumberProp Is Nothing OrElse partNumberProp.Value Is Nothing Then
            Return ""
        End If
        Return CStr(partNumberProp.Value)
    Catch
        Return ""
    End Try
End Function

Function GetRevisionFromDocument(doc As Document) As String
    If doc Is Nothing Then
        Return ""
    End If

    ' Revision Number is shown on Inventor's iProperties > Project tab.
    Try
        Dim trackingProps As PropertySet = doc.PropertySets.Item("Design Tracking Properties")
        Dim revisionProp As Inventor.Property = trackingProps.Item("Revision Number")
        If Not revisionProp Is Nothing AndAlso Not revisionProp.Value Is Nothing Then
            Return CStr(revisionProp.Value).Trim()
        End If
    Catch
    End Try

    ' Fallback for templates/files that expose it in Summary Information.
    Try
        Dim summaryProps As PropertySet = doc.PropertySets.Item("Inventor Summary Information")
        Dim revisionProp As Inventor.Property = summaryProps.Item("Revision Number")
        If Not revisionProp Is Nothing AndAlso Not revisionProp.Value Is Nothing Then
            Return CStr(revisionProp.Value).Trim()
        End If
    Catch
    End Try

    Return ""
End Function

Function GetCustomPropertyValue(doc As Document, propertyName As String) As String
    Try
        Dim customProps As PropertySet = doc.PropertySets.Item("Inventor User Defined Properties")
        Dim prop As Inventor.Property = customProps.Item(propertyName)
        If prop Is Nothing OrElse prop.Value Is Nothing Then
            Return ""
        End If
        Return CStr(prop.Value).Trim()
    Catch
        Return ""
    End Try
End Function



Function FilterPartNumber(partNumber As String) As String
    If String.IsNullOrEmpty(partNumber) Then
        Return ""
    End If

    Dim cleaned As String = partNumber.Trim().ToUpperInvariant()
    Dim strictFsiPattern As String = "FSI\s*-\s*([A-Z0-9]{2,3})\s*-\s*([A-Z0-9]{2,3})\s*-\s*([A-Z0-9]{2,3})"
    Dim matchResult As Match = Regex.Match(cleaned, strictFsiPattern, RegexOptions.IgnoreCase)

    If matchResult.Success Then
        Dim segment1 As String = matchResult.Groups(1).Value.ToUpperInvariant()
        Dim segment2 As String = matchResult.Groups(2).Value.ToUpperInvariant()
        Dim segment3 As String = matchResult.Groups(3).Value.ToUpperInvariant()
        Return "FSI-" & segment1 & "-" & segment2 & "-" & segment3
    End If

    ' Fallback: if user mistyped one segment length (missing digit, etc.),
    ' still keep the first FSI-like token in PART_NUMBER_FILTER and normalize spaces.
    Dim looseFsiPattern As String = "FSI\s*-\s*[A-Z0-9-\s]+"
    matchResult = Regex.Match(cleaned, looseFsiPattern, RegexOptions.IgnoreCase)
    If matchResult.Success Then
        Dim normalized As String = Regex.Replace(matchResult.Value.ToUpperInvariant(), "\s*-\s*", "-")
        Return normalized.Trim("-"c)
    End If

    Return ""
End Function

Function CsvEscape(value As String) As String
    If value Is Nothing Then
        value = ""
    End If

    Return Chr(34) & value.Replace(Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function

Function CreateHighlightedManifestWorkbook(manifestCsvPath As String, outputXlsxPath As String) As String
    If String.IsNullOrEmpty(manifestCsvPath) OrElse Not IOFile.Exists(manifestCsvPath) Then
        Return "Not created"
    End If

    Dim xlsxPath As String = outputXlsxPath
    Dim excelApp As Object = Nothing
    Dim workbook As Object = Nothing

    Try
        excelApp = CreateObject("Excel.Application")
        excelApp.DisplayAlerts = False
        excelApp.Visible = False

        workbook = excelApp.Workbooks.Open(manifestCsvPath)
        Dim sheet As Object = workbook.Worksheets(1)
        Do While workbook.Worksheets.Count > 1
            workbook.Worksheets(workbook.Worksheets.Count).Delete()
        Loop
        sheet.Name = "PDF_BOM_ORDER"
        Dim rawPartColumn As Integer = FindHeaderColumn(sheet, "RAW PART NUMBER")
        Dim lastRow As Integer = CInt(sheet.Cells(sheet.Rows.Count, 1).End(-4162).Row) ' xlUp

        Dim quantityColumn As Integer = FindHeaderColumn(sheet, "Quantity")
        Dim finishColumn As Integer = FindHeaderColumn(sheet, "Finish")
        Dim materialColumn As Integer = FindHeaderColumn(sheet, "Material")
        Dim revisionColumn As Integer = FindHeaderColumn(sheet, "Revision")
        If rawPartColumn > 0 Then
            HighlightInvalidRawPartNumbers(sheet, rawPartColumn, lastRow)
            BuildPartCountSheet(workbook, sheet, rawPartColumn, quantityColumn, finishColumn, materialColumn, revisionColumn, lastRow)
        End If

        ' Keep the BOM order worksheet active so downstream XLSX readers use it.
        sheet.Activate()
        workbook.SaveAs(xlsxPath, 51) ' xlOpenXMLWorkbook
        workbook.Close(False)
        excelApp.Quit()
        Return xlsxPath
    Catch
        Try
            If Not workbook Is Nothing Then workbook.Close(False)
        Catch
        End Try
        Try
            If Not excelApp Is Nothing Then excelApp.Quit()
        Catch
        End Try
        Return "Not created (Excel unavailable or failed)"
    End Try
End Function

Function FindHeaderColumn(sheet As Object, headerName As String) As Integer
    If sheet Is Nothing Then
        Return 0
    End If

    For col As Integer = 1 To 200
        Dim value As Object = sheet.Cells(1, col).Value
        Dim headerValue As String = ""
        If Not value Is Nothing Then
            headerValue = CStr(value).Trim()
        End If

        If String.Equals(headerValue, headerName, StringComparison.OrdinalIgnoreCase) Then
            Return col
        End If
        If String.IsNullOrEmpty(headerValue) Then
            Exit For
        End If
    Next

    Return 0
End Function

Sub HighlightInvalidRawPartNumbers(sheet As Object, columnIndex As Integer, lastRow As Integer)
    If sheet Is Nothing OrElse columnIndex <= 0 OrElse lastRow < 2 Then
        Return
    End If

    Dim strictPattern As String = "^FSI\s*-\s*[A-Z0-9]{3}\s*-\s*[A-Z0-9]{2}\s*-\s*[A-Z0-9]{3}$"

    For row As Integer = 2 To lastRow
        Dim valueObj As Object = sheet.Cells(row, columnIndex).Value
        Dim value As String = ""
        If Not valueObj Is Nothing Then
            value = CStr(valueObj).Trim()
        End If

        If Not Regex.IsMatch(value, strictPattern, RegexOptions.IgnoreCase) Then
            sheet.Cells(row, columnIndex).Interior.Color = RGB(255, 245, 157)
        End If
    Next
End Sub

Sub BuildPartCountSheet(workbook As Object, sourceSheet As Object, rawPartColumn As Integer, quantityColumn As Integer, finishColumn As Integer, materialColumn As Integer, revisionColumn As Integer, lastRow As Integer)
    If workbook Is Nothing OrElse sourceSheet Is Nothing OrElse rawPartColumn <= 0 OrElse lastRow < 2 Then
        Return
    End If

    Dim countSheet As Object = Nothing
    Try
        countSheet = workbook.Worksheets("PART_COUNTS")
        countSheet.Cells.Clear()
    Catch
        countSheet = workbook.Worksheets.Add(After:=workbook.Worksheets(workbook.Worksheets.Count))
        countSheet.Name = "PART_COUNTS"
    End Try

    Dim counts As Object = CreateObject("Scripting.Dictionary")
    counts.CompareMode = 1 ' TextCompare
    Dim finishByPart As Object = CreateObject("Scripting.Dictionary")
    finishByPart.CompareMode = 1 ' TextCompare
    Dim materialByPart As Object = CreateObject("Scripting.Dictionary")
    materialByPart.CompareMode = 1 ' TextCompare
    Dim revisionByPart As Object = CreateObject("Scripting.Dictionary")
    revisionByPart.CompareMode = 1 ' TextCompare

    For row As Integer = 2 To lastRow
        Dim valueObj As Object = sourceSheet.Cells(row, rawPartColumn).Value
        Dim value As String = ""
        If Not valueObj Is Nothing Then
            value = CStr(valueObj).Trim()
        End If
        If String.IsNullOrEmpty(value) Then
            Continue For
        End If

        Dim qty As Integer = 1
        If quantityColumn > 0 Then
            Try
                Dim qtyObj As Object = sourceSheet.Cells(row, quantityColumn).Value
                If Not qtyObj Is Nothing Then
                    qty = CInt(Math.Round(CDbl(qtyObj)))
                End If
            Catch
                qty = 1
            End Try
        End If
        If qty < 1 Then
            qty = 1
        End If

        If counts.Exists(value) Then
            counts(value) = CInt(counts(value)) + qty
        Else
            counts.Add(value, qty)
        End If

        If finishColumn > 0 Then
            Dim finishValue As String = ""
            Try
                Dim finishObj As Object = sourceSheet.Cells(row, finishColumn).Value
                If Not finishObj Is Nothing Then
                    finishValue = CStr(finishObj).Trim()
                End If
            Catch
                finishValue = ""
            End Try
            If Not String.IsNullOrEmpty(finishValue) Then
                If Not finishByPart.Exists(value) OrElse String.IsNullOrEmpty(CStr(finishByPart(value))) Then
                    finishByPart(value) = finishValue
                End If
            End If
        End If

        If materialColumn > 0 Then
            Dim materialValue As String = ""
            Try
                Dim materialObj As Object = sourceSheet.Cells(row, materialColumn).Value
                If Not materialObj Is Nothing Then
                    materialValue = CStr(materialObj).Trim()
                End If
            Catch
                materialValue = ""
            End Try
            If Not String.IsNullOrEmpty(materialValue) Then
                If Not materialByPart.Exists(value) OrElse String.IsNullOrEmpty(CStr(materialByPart(value))) Then
                    materialByPart(value) = materialValue
                End If
            End If
        End If

        If revisionColumn > 0 Then
            Dim revisionValue As String = ""
            Try
                Dim revisionObj As Object = sourceSheet.Cells(row, revisionColumn).Value
                If Not revisionObj Is Nothing Then
                    revisionValue = CStr(revisionObj).Trim()
                End If
            Catch
                revisionValue = ""
            End Try
            If Not String.IsNullOrEmpty(revisionValue) Then
                If Not revisionByPart.Exists(value) OrElse String.IsNullOrEmpty(CStr(revisionByPart(value))) Then
                    revisionByPart(value) = revisionValue
                End If
            End If
        End If
    Next

    countSheet.Cells(1, 1).Value = "PART NUMBER"
    countSheet.Cells(1, 2).Value = "COUNT"
    countSheet.Cells(1, 3).Value = "REVISION"
    countSheet.Cells(1, 4).Value = "FINISH"
    countSheet.Cells(1, 5).Value = "MATERIAL"

    Dim outputRow As Integer = 2
    For Each key As Object In counts.Keys
        countSheet.Cells(outputRow, 1).Value = CStr(key)
        countSheet.Cells(outputRow, 2).Value = CInt(counts(key))
        If revisionByPart.Exists(key) Then
            countSheet.Cells(outputRow, 3).Value = CStr(revisionByPart(key))
        End If
        If finishByPart.Exists(key) Then
            countSheet.Cells(outputRow, 4).Value = CStr(finishByPart(key))
        End If
        If materialByPart.Exists(key) Then
            countSheet.Cells(outputRow, 5).Value = CStr(materialByPart(key))
        End If
        outputRow += 1
    Next

    If outputRow > 2 Then
        Dim sortRange As Object = countSheet.Range("A1:E" & CStr(outputRow - 1))
        sortRange.Sort(Key1:=countSheet.Range("B2"), Order1:=2, Header:=1) ' descending by count
    End If

    countSheet.Columns("A:E").AutoFit()
End Sub

Function ParseDrawingRootsInput(input As String) As List(Of String)
    Dim roots As New List(Of String)

    If String.IsNullOrEmpty(input) Then
        Return roots
    End If

    Dim tokens() As String = input.Split(";"c)
    For Each token As String In tokens
        Dim trimmed As String = token.Trim()
        If Not String.IsNullOrEmpty(trimmed) Then
            roots.Add(trimmed)
        End If
    Next

    Return roots
End Function

Function ResolveDrawingSearchRoots(projectRoot As String, drawingsRootOverrides As List(Of String)) As List(Of String)
    Dim roots As New List(Of String)
    Dim seen As New HashSet(Of String)(StringComparer.OrdinalIgnoreCase)

    For Each root As String In drawingsRootOverrides
        If String.IsNullOrEmpty(root) Then
            Continue For
        End If

        If IODirectory.Exists(root) AndAlso Not seen.Contains(root) Then
            roots.Add(root)
            seen.Add(root)
        End If
    Next

    If roots.Count = 0 AndAlso IODirectory.Exists(projectRoot) Then
        roots.Add(projectRoot)
    End If

    Return roots
End Function

Sub BuildDrawingIndex(searchRoots As List(Of String), drawingIndex As Dictionary(Of String, String))
    For Each searchRoot As String In searchRoots
        IndexDrawingFilesUnderRoot(searchRoot, drawingIndex)
    Next
End Sub

Sub IndexDrawingFilesUnderRoot(searchRoot As String, drawingIndex As Dictionary(Of String, String))
    If String.IsNullOrEmpty(searchRoot) OrElse Not IODirectory.Exists(searchRoot) Then
        Return
    End If

    If ShouldSkipFolder(searchRoot) Then
        Return
    End If

    Try
        Dim idwFiles() As String = IODirectory.GetFiles(searchRoot, "*.idw", System.IO.SearchOption.TopDirectoryOnly)
        Dim dwgFiles() As String = IODirectory.GetFiles(searchRoot, "*.dwg", System.IO.SearchOption.TopDirectoryOnly)

        For Each path As String In idwFiles
            AddDrawingIndexCandidate(drawingIndex, path)
        Next

        For Each path As String In dwgFiles
            AddDrawingIndexCandidate(drawingIndex, path)
        Next
    Catch
        ' Ignore access issues and continue with other folders.
    End Try

    Try
        Dim childDirs() As String = IODirectory.GetDirectories(searchRoot, "*", System.IO.SearchOption.TopDirectoryOnly)
        For Each childDir As String In childDirs
            If ShouldSkipFolder(childDir) Then
                Continue For
            End If
            IndexDrawingFilesUnderRoot(childDir, drawingIndex)
        Next
    Catch
        ' Ignore access issues and continue with other folders.
    End Try
End Sub

Sub AddDrawingIndexCandidate(drawingIndex As Dictionary(Of String, String), candidatePath As String)
    Dim key As String = IOPath.GetFileNameWithoutExtension(candidatePath).ToUpperInvariant()
    If String.IsNullOrEmpty(key) Then
        Return
    End If

    If Not drawingIndex.ContainsKey(key) Then
        drawingIndex(key) = candidatePath
        Return
    End If

    Dim existingPath As String = drawingIndex(key)
    Try
        If IOFile.GetLastWriteTime(candidatePath) > IOFile.GetLastWriteTime(existingPath) Then
            drawingIndex(key) = candidatePath
        End If
    Catch
        ' If timestamps cannot be read, keep the existing indexed path.
    End Try
End Sub

Function ShouldSkipFolder(folderPath As String) As Boolean
    If String.IsNullOrEmpty(folderPath) Then
        Return False
    End If

    Dim folderName As String = IOPath.GetFileName(folderPath)
    Return String.Equals(folderName, "OldVersions", StringComparison.OrdinalIgnoreCase)
End Function

Function FindDrawingForModel(modelPath As String, drawingIndex As Dictionary(Of String, String)) As String
    Dim baseName As String = IOPath.GetFileNameWithoutExtension(modelPath)
    Dim exactBaseKey As String = baseName.ToUpperInvariant()

    ' Search only the selected drawing roots by exact same base filename.
    ' The index keeps the newest modified candidate when duplicates exist.
    If Not String.IsNullOrEmpty(exactBaseKey) AndAlso drawingIndex.ContainsKey(exactBaseKey) Then
        Return drawingIndex(exactBaseKey)
    End If

    Return ""
End Function

Function ExportDrawingToPdf(drawingPath As String, pdfPath As String) As Boolean
    Dim drawDoc As DrawingDocument = Nothing
    Dim previousSilentOperation As Boolean = False
    Dim silentOperationCaptured As Boolean = False
    Dim eventsSettingName As String = ""
    Dim previousEventsEnabled As Boolean = False
    Dim eventsSettingCaptured As Boolean = False

    Try
        ' Suppress prompts and disable iLogic event-driven rules while opening drawings.
        ' This avoids errors from missing external event rules in referenced documents.
        Try
            previousSilentOperation = ThisApplication.SilentOperation
            silentOperationCaptured = True
            ThisApplication.SilentOperation = True
        Catch
            ' Ignore if property is unavailable.
        End Try

        CaptureAndSetILogicEventsSetting(iLogicVb.Automation, "RulesOnEventsEnabled", eventsSettingName, previousEventsEnabled, eventsSettingCaptured)
        If Not eventsSettingCaptured Then
            CaptureAndSetILogicEventsSetting(iLogicVb.Automation, "RulesEnabled", eventsSettingName, previousEventsEnabled, eventsSettingCaptured)
        End If

        drawDoc = CType(ThisApplication.Documents.Open(drawingPath, True), DrawingDocument)

        Dim pdfAddIn As TranslatorAddIn = CType(
            ThisApplication.ApplicationAddIns.ItemById("{0AC6FD96-2F4D-42CE-8BE0-8AEA580399E4}"),
            TranslatorAddIn
        )

        Dim context As TranslationContext = ThisApplication.TransientObjects.CreateTranslationContext
        context.Type = IOMechanismEnum.kFileBrowseIOMechanism

        Dim options As NameValueMap = ThisApplication.TransientObjects.CreateNameValueMap
        If pdfAddIn.HasSaveCopyAsOptions(drawDoc, context, options) Then
            options.Value("All_Color_AS_Black") = False
            options.Value("Remove_Line_Weights") = False
            options.Value("Vector_Resolution") = 400
            options.Value("Sheet_Range") = PrintRangeEnum.kPrintAllSheets
        End If

        Dim data As DataMedium = ThisApplication.TransientObjects.CreateDataMedium
        data.FileName = pdfPath

        pdfAddIn.SaveCopyAs(drawDoc, context, options, data)
        Return True

    Catch ex As Exception
        MessageBox.Show("Failed PDF export for: " & drawingPath & vbCrLf & ex.Message, "iLogic")
        Return False

    Finally
        If Not drawDoc Is Nothing Then
            drawDoc.Close(True)
        End If

        If eventsSettingCaptured AndAlso Not String.IsNullOrEmpty(eventsSettingName) Then
            Try
                CallByName(iLogicVb.Automation, eventsSettingName, CallType.Set, previousEventsEnabled)
            Catch
                ' Ignore restore failures.
            End Try
        End If

        If silentOperationCaptured Then
            Try
                ThisApplication.SilentOperation = previousSilentOperation
            Catch
                ' Ignore restore failures.
            End Try
        End If
    End Try
End Function

Sub CaptureAndSetILogicEventsSetting(autoObj As Object, propertyName As String, ByRef capturedName As String, ByRef previousValue As Boolean, ByRef captured As Boolean)
    If captured Then
        Return
    End If

    Try
        previousValue = CBool(CallByName(autoObj, propertyName, CallType.Get))
        CallByName(autoObj, propertyName, CallType.Set, False)
        capturedName = propertyName
        captured = True
    Catch
        ' Property not available in this environment/version.
    End Try
End Sub
