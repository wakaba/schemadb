
window.onload = function () {
  var codeParent = document.getElementsByTagName ('pre')[0].firstChild;

  var req = new XMLHttpRequest ();
  req.open ('GET', 'annotation.txt', true);
  req.onreadystatechange = function () {
    if (req.readyState == 4) {
      if (req.status >= 200 && req.status < 400) {
        setStatus ($('status'), 'info',
                   'Annotations are loaded (' + req.status + ' ' +
                   req.statusText + ').');

        var aLines = req.responseText.split (/\x0D?\x0A/);
        var vn = function (v) {
          return v.replace (/\\t;/g, '\t').replace (/\\n;/g, '\n')
              .replace (/\\\\;/g, '\\');
        }; // v
        if (!document.SAItems) document.SAItems = [];
        for (var i = 0; i < aLines.length; i++) {
          if (aLines[i].length == 0) continue;
          var v = aLines[i].split (/\t/, 5);
          var item = {
            id: vn (v[0] || ''),
            lineNumber: parseInt (vn (v[1] || '')),
            type: vn (v[2] || ''),
            name: vn (v[3] || ''),
            comment: vn (v[4] || '')
          };
          if (!document.SAItems[item.lineNumber]) {
            document.SAItems[item.lineNumber] = [];
          }
          document.SAItems[item.lineNumber].push (item);
        }

        document.SALineElement = [];  
        var lines = codeParent.childNodes;
        var linesL = lines.length;
        var j = 1;
        for (var i = 0; i < linesL; i++) {
          var line = lines[i];
          if (line.nodeType != 1) continue;
          line.SALineNumber = j++;
          line.onclick = function (e) {
            createSALinePanel (this, e.pageX, e.pageY);
          }; // line.onclick
          document.SALineElement[line.SALineNumber] = line;
          if (document.SAItems[line.SALineNumber] &&
              document.SAItems[line.SALineNumber].length > 0) {
            line.className = 'line sa-with-annotation';
          }
        } // i
      } else {
        setStatus ($('status'), 'error',
                   'Can\'t load annotations (' + req.status + ' ' +
                   req.statusText + ').');
      }
    }
  };
  req.send (null);
}; // window.onload

function $(id) {
  return document.getElementById (id);
} // $

function setStatus (e, c, s) {
  e.className = c;
  e.textContent = s;
} // setStatus

function createSALinePanel (line, x, y) {
  var panel;
  var lineNumber = line.SALineNumber;
  if (document.SALinePanels && document.SALinePanels[lineNumber]) {
    panel = document.SALinePanels[lineNumber];
  } else {
    panel = document.createElement ('div');
    panel.style.position = 'absolute';
    panel.className = 'sa-line-panel';

    var panelLabel = document.createElement ('legend');
    panelLabel.textContent = 'Line ' + lineNumber;
    panelLabel.onmousedown = function () {
      document.body.appendChild (this.parentNode); // z-index
    };
    panel.appendChild (panelLabel);

    var closeButton = document.createElement ('button');
    closeButton.type = 'button';
    closeButton.textContent = '\u00D7';
    closeButton.onclick = function () {
      document.body.removeChild (document.SALinePanels[lineNumber]);
      delete document.SALinePanels[lineNumber];
    };
    closeButton.className = 'sa-line-panel-close';
    panel.appendChild (closeButton);

    var panelStatus = document.createElement ('span');
    var entries = document.createElement ('ul');
    var items = document.SAItems ? document.SAItems[lineNumber] : null;
    if (items) {
      for (var i = 0; i < items.length; i++) {
        var entry = createSALineEntry (items[i], panelStatus);
        entries.appendChild (entry);
      }
    }
    panel.appendChild (entries);

    var toolbar = document.createElement ('menu');
    var addButton = document.createElement ('button');
    addButton.textContent = 'Add';
    addButton.type = 'button';
    addButton.onclick = function () {
      var req = new XMLHttpRequest ();
      req.open ('POST', 'annotation.txt', true);
      req.onreadystatechange = function () {
        if (req.readyState == 4) {
          if (req.status >= 200 && req.status < 400) {
            setStatus (panelStatus, 'info',
                'New entry created (' + req.status + ' ' +
                req.statusText + ').');

            var item = {
              type: "", name: "", comment: "", lineNumber: lineNumber,
              id: req.responseText
            };
            if (!document.SAItems[lineNumber]) document.SAItems[lineNumber] = [];
            document.SAItems[lineNumber].push (item);
            var entry = createSALineEntry (item, panelStatus);
            entries.appendChild (entry);
            document.SALineElement[lineNumber].className
                = 'line sa-with-annotation';
          } else {
            setStatus (panelStatus, 'error',
                'Can\'t create new entry (' + req.status + ' ' +
                req.statusText + ').');
          }
        }
      };
      req.send (null);
    };
    toolbar.appendChild (addButton);
    toolbar.appendChild (panelStatus);
    panel.appendChild (toolbar);

    document.body.appendChild (panel);
    if (!document.SALinePanels) document.SALinePanels = [];
    document.SALinePanels[lineNumber] = panel;
  }
  panel.style.top = y + 'px';
  panel.style.left = x + 'px';
} // createSALinePanel

function createSALineEntry (item, panelStatus) {
  var entry = document.createElement ('li');
  var typeSelection = document.createElement ('select');
  var opt = typeSelection.appendChild (document.createElement ('option'));
  opt.textContent = '(none)';
  opt.value = '';
  var optgroup1 = document.createElement ('optgroup');
  optgroup1.label = 'Element';
  optgroup1.appendChild (document.createElement ('option'))
      .textContent = 'Element';
  optgroup1.appendChild (document.createElement ('option'))
      .textContent = 'Attributes for element';
  optgroup1.appendChild (document.createElement ('option'))
      .textContent = 'Content model for element';
  optgroup1.appendChild (document.createElement ('option'))
      .textContent = 'Element reference';
  typeSelection.appendChild (optgroup1);
  var optgroup2 = document.createElement ('optgroup');
  optgroup2.label = 'Attribute';
  optgroup2.appendChild (document.createElement ('option'))
      .textContent = 'Attribute';
  optgroup2.appendChild (document.createElement ('option'))
      .textContent = 'Attribute reference';
  optgroup2.appendChild (document.createElement ('option'))
      .textContent = 'Attribute set';
  optgroup2.appendChild (document.createElement ('option'))
      .textContent = 'Attribute set reference';
  typeSelection.appendChild (optgroup2);
  var optgroup3 = document.createElement ('optgroup');
  optgroup3.label = 'Type';
  optgroup3.appendChild (document.createElement ('option'))
      .textContent = 'Content set';
  optgroup3.appendChild (document.createElement ('option'))
      .textContent = 'Content set reference';
  optgroup3.appendChild (document.createElement ('option'))
      .textContent = 'Value type';
  optgroup3.appendChild (document.createElement ('option'))
      .textContent = 'Notation';
  typeSelection.appendChild (optgroup3);
  var optgroup4 = document.createElement ('optgroup');
  optgroup4.label = 'Entity';
  optgroup4.appendChild (document.createElement ('option'))
      .textContent = 'Character entity';
  optgroup4.appendChild (document.createElement ('option'))
      .textContent = 'Parameter entity';
  optgroup4.appendChild (document.createElement ('option'))
      .textContent = 'Parameter entity reference';
  typeSelection.appendChild (optgroup4);
  typeSelection.onchange = function () {
    this.parentNode.SAItem.type = this.value;
    this.parentNode.SaveSAItem ();
  };
  entry.appendChild (typeSelection);

  var nameInput = document.createElement ('input');
  nameInput.type = 'text';
  nameInput.className = 'sa-object-name';
  nameInput.onchange = function () {
    this.parentNode.SAItem.name = this.value;
    this.parentNode.SaveSAItem ();
  };
  entry.appendChild (nameInput);

  var commentInput = document.createElement ('textarea');
  commentInput.className = 'sa-object-comment';
  commentInput.wrap = 'soft';
  commentInput.onchange = function () {
    this.parentNode.SAItem.comment = this.value;
    this.parentNode.SaveSAItem ();
  };
  entry.appendChild (commentInput);

  var deleteButton = document.createElement ('button');
  deleteButton.type = 'button';
  deleteButton.textContent = 'Delete';
  deleteButton.onclick = function () {
    var req = new XMLHttpRequest ();
    req.open ('DELETE', 'annotation/' + item.id, true);
    req.onreadystatechange = function () {
      if (req.readyState == 4) {
        if (req.status >= 200 && req.status < 400) {
          setStatus (panelStatus, 'info',
              'Entry deleted (' + req.status + ' ' +
              req.statusText + ').');

          var items = document.SAItems[item.lineNumber];
          for (var i = 0; i < items.length; i++) {
            if (items[i].id == item.id) {
              items.splice (i, 1);
              break;
            }
          }
          entry.parentNode.removeChild (entry);
          if (document.SAItems[item.lineNumber].length == 0) {
            document.SALineElement[item.lineNumber].className = 'line';
          }
        } else {
          setStatus (panelStatus, 'error',
              'Can\'t delete entry (' + req.status + ' ' +
              req.statusText + ').');
        }
      }
    };
    req.send (null);
  };
  entry.appendChild (deleteButton);

  typeSelection.value = item.type;
  nameInput.value = item.name;
  commentInput.value = item.comment;
  entry.SAItem = item;
  entry.SaveSAItem = function () {
    var v = function (s) {
      return s.replace (/\\/g, '\\\\;').replace (/\t/g, '\\t;')
          .replace (/\x0D?\x0A/g, '\\n;').replace (/\x0D/g, '\\n;');
    };
    var text = [v (item.id), v (item.lineNumber.toString ()),
                v (item.type), v (item.name), v (item.comment)].join ("\t");
    var req = new XMLHttpRequest ();
    req.open ('PUT', 'annotation/' + item.id + '.txt', true);
    req.onreadystatechange = function () {
      if (req.readyState == 4) {
        if (req.status >= 200 && req.status < 400) {
          setStatus (panelStatus, 'info',
              'Entry saved (' + req.status + ' ' +
              req.statusText + ').');
        } else {
          setStatus (panelStatus, 'error',
              'Can\'t save entry (' + req.status + ' ' +
              req.statusText + ').');
        }
      }
    };
    req.send (text);
  };

  return entry;
} // createSALineEntry