import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

AppDialog {
    id: dialog
    objectName: "comexConnectionDialog"
    title: "Acesso ao Comex Stat"
    readonly property bool fileChoosing: pairingFile.visible
    readonly property bool canSave: !controller.state.busy && !controller.state.metadataBusy && !comexAccess.state.testing
    onAboutToShow: {
        comexAccess.prepare();
        shared.checked = comexAccess.state.enabled;
        address.text = comexAccess.state.url;
        secret.text = comexAccess.state.token;
    }
    Label {
        Layout.fillWidth: true
        text: "O acesso inicia automaticamente. Se este computador já hospeda a central da empresa, ela é retomada em segundo plano ao abrir o programa."
        color: Theme.muted
        font.pixelSize: 12
        wrapMode: Text.WordWrap
    }
    AppCheck {
        id: shared
        objectName: "sharedComexMode"
        text: "Usar central da empresa na rede"
    }
    ColumnLayout {
        visible: shared.checked
        Layout.fillWidth: true
        spacing: 6
        Label {
            text: "Endereço da central"
            color: Theme.muted
            font.pixelSize: 11
        }
        TextField {
            id: address
            objectName: "centralAddress"
            Layout.fillWidth: true
            placeholderText: "http://servidor:8767"
            selectByMouse: true
            maximumLength: 512
            Accessible.name: "Endereço da Central de Consultas"
        }
        Label {
            text: "Chave de acesso"
            color: Theme.muted
            font.pixelSize: 11
        }
        TextField {
            id: secret
            objectName: "centralToken"
            Layout.fillWidth: true
            echoMode: TextInput.Password
            selectByMouse: true
            maximumLength: 256
            Accessible.name: "Chave de acesso à central"
        }
        ActionButton {
            objectName: "testCentral"
            text: comexAccess.state.testing ? "Verificando…" : "Testar conexão"
            enabled: !comexAccess.state.testing
            onClicked: comexAccess.test(address.text, secret.text)
        }
    }
    Label {
        Layout.fillWidth: true
        visible: !shared.checked
        text: "Selecione o período e consulte. A fila, os arquivos oficiais e os certificados do Windows são administrados pelo aplicativo."
        color: Theme.muted
        font.pixelSize: 12
        wrapMode: Text.WordWrap
    }
    Label {
        Layout.fillWidth: true
        visible: comexAccess.state.message.length > 0
        text: comexAccess.state.message
        textFormat: Text.PlainText
        color: comexAccess.state.error ? Theme.danger : Theme.muted
        font.pixelSize: 12
        wrapMode: Text.WordWrap
    }
    Label {
        Layout.fillWidth: true
        visible: !dialog.canSave && !comexAccess.state.testing
        text: "Aguarde a consulta em andamento para salvar a conexão."
        color: Theme.muted
        font.pixelSize: 11
        wrapMode: Text.WordWrap
    }
    ActionButton {
        objectName: "importCentralConnection"
        Layout.fillWidth: true
        text: "Importar conexão da empresa"
        iconName: "folder"
        enabled: dialog.canSave
        onClicked: pairingFile.open()
    }
    ActionButton {
        objectName: "saveCentralConnection"
        Layout.fillWidth: true
        text: "Salvar conexão"
        primary: true
        enabled: dialog.canSave
        onClicked: if (comexAccess.save(address.text, secret.text, shared.checked))
            dialog.close()
    }
    Rectangle {
        Layout.fillWidth: true
        height: 1
        color: Theme.line
    }
    ActionButton {
        objectName: "openComexCentral"
        Layout.fillWidth: true
        text: "Abrir central neste computador"
        subtle: true
        onClicked: comexAccess.openCentral()
    }
    FileDialog {
        id: pairingFile
        objectName: "centralPairingFile"
        title: "Importar conexão da empresa"
        nameFilters: ["Conexão LIARTE (*.liarte-conexao)"]
        onAccepted: if (comexAccess.importFile(selectedFile))
            dialog.close()
    }
}
