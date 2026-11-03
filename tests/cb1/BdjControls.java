/* SPDX-License-Identifier: GPL-2.0-only */
import java.awt.Dimension;
import org.videolan.StreamInfo;
import org.videolan.TIClip;
import org.videolan.media.content.playlist.BackgroundVideoPresentationControlImpl;
import org.videolan.media.content.playlist.StreamControl;
import org.bluray.ti.PlayItemImpl;
import org.davic.media.LanguageNotAvailableException;
import javax.tv.service.navigation.ServiceComponent;

/** Exercise the real matched libbluray classes; no disc/player replacements. */
public final class BdjControls {
    private static StreamInfo stream(int format, String language) {
        return new StreamInfo((byte)0x24, (byte)format, (byte)1, (char)0,
                              language, (byte)3, (byte)0);
    }
    private static final class Background extends BackgroundVideoPresentationControlImpl {
        final StreamInfo stream;
        Background(StreamInfo stream) { super(null); this.stream = stream; }
        protected StreamInfo getCurrentStream() { return stream; }
    }
    private static final class Languages extends StreamControl {
        int selected;
        protected StreamInfo[] getStreams() {
            return new StreamInfo[] { stream(8, "eng"), stream(8, "eng") };
        }
        protected void setStreamNumber(int num) { selected = num; }
        public int getCurrentStreamNumber() { return selected; }
    }
    private static final class Item extends PlayItemImpl {
        Item(TIClip clip) { super(1, 1, clip, null); }
    }
    public static void main(String[] args) throws Exception {
        int[][] sizes = {{0,0},{720,480},{720,576},{720,480},{1920,1080},
                         {1280,720},{1920,1080},{720,576},{3840,2160}};
        for (int i = -1; i <= 9; i++) {
            int format = i == 9 ? 255 : i;
            StreamInfo input = format < 0 ? null : stream(format, "eng");
            Dimension expected = i < 1 || i > 8 ? new Dimension(0,0)
                : new Dimension(sizes[i][0], sizes[i][1]);
            Dimension actual = new Background(input).getInputVideoSize();
            if (!expected.equals(actual))
                throw new AssertionError("Format " + format + ": " + actual + " != " + expected);
        }
        Languages languages = new Languages();
        languages.selectLanguage("eng");
        if (languages.selected != 1) throw new AssertionError("Select the first matching stream");
        try {
            languages.selectLanguage("fra");
            throw new AssertionError("Missing language must fail");
        } catch (LanguageNotAvailableException expected) {}
        StreamInfo[] empty = new StreamInfo[0];
        TIClip clip = new TIClip(1, new StreamInfo[] {stream(8,"vid")},
            new StreamInfo[] {stream(8,"eng"),stream(8,"fra")},
            new StreamInfo[] {stream(8,"sub")},empty,empty,empty);
        ServiceComponent[] components = new Item(clip).getComponents();
        if (components.length != 4 || !components[1].getAssociatedLanguage().equals("eng") ||
            !components[2].getAssociatedLanguage().equals("fra") ||
            !components[3].getAssociatedLanguage().equals("sub"))
            throw new AssertionError("Components must use their own stream list");
        System.out.println("PASS dimensions, language selection and component inventories");
    }
}
