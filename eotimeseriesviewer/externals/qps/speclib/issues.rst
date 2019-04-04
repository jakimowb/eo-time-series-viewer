
Spectral Viewer:
- Fenster mit Sprektren ca. 75% der Breite, so dass man nur die ersten beiden Spalten der Tabelle (Actions und Namen!) sieht.
- die Felder FID, source, values, style sind optional und per default ausgeblendet,
  man kann sie über drop down mit checkbox unterhalt tabelle einblenden.
  Weitere Features (neu generierte oder zusätzliche aus geöffneter Speclib sind per default sichtbar und rechts des Namens)
  [hier wollen wir nah an ENVI sein!]

Nur Action + Name

- Button in spectral library viewer werden getrennt. Spektrenteil wie bisher links oben.
  Attributteil (ab Bleistift) entweder rechts in Leiste aber linker Kante der Tabelle oder unter der Tabelle!

- neuer Button rechts bei Spektralbutton: "Move selected pixels to [dropdown] "New spectral library"; "Spectral library #2"..."
Je nachdem was schon da ist. "New spectral library" induziert neues Fenster, welches mit gleichen Maps verknüpft ist.
- Die beiden Linken Button werden durch ein DropdDown mit Optionen "View selected spectrum" "Collect selected spetrum" ersetzt. So entkoppeln wir die Aktivierung und den Umgang und bennen es gut sichtbar und explizit. Daneben der Add Button, der nur sensitiv ist, wenn die erste Option gewählt und das Pixel noch nicht ge-added wurde.

QMenu
QAction -> add spectral profile(s) ("view")
QAction -> add spectral profile(s) automatically
QAction ->

less buttons


- Ich würde für einen zusätzliche "Clear" Button plädieren, der alle Spektren löscht.
QAction clear all als button


- Reload button unklar (Funktion und somit Nutzen)
hide?

- Ein Dateiname einer importierten Spektralbibliothek kann "Source" werden, wenn denn keine Source in der SpecLib angegeben ist (?)
???


- Selektion von Spektren in Chart und Tabelle sollte immer beidseitig zu Auswahl (links fette Linie, rechts blaue Zeile) führen

- Auswahl muss auch gut klappen und sichtbar sein, wenn editing mode an ist.

problem: select by API does not highlight rows in the same way as selected by mouse
move & copy to selected to new / existing speclib
add select by expression



