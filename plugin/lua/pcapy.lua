-- Pcapy: turns the per-packet comment written by the phone ("app=<package> uid=<uid>")
-- into filterable fields:  pcapy.app  and  pcapy.uid
--
--   pcapy.app == "com.example.shop"        packets of one app
--   pcapy.uid == 10123                     packets of one Android user id
--   pcapy.app                              only packets that have an owner
--
-- Add the "App" column from the Pcapy profile (see install.sh), or right-click the
-- field in the packet details > Apply as Column.

local pcapy = Proto("pcapy", "Pcapy")

local f_app = ProtoField.string("pcapy.app", "App")
local f_uid = ProtoField.uint32("pcapy.uid", "UID", base.DEC)
pcapy.fields = { f_app, f_uid }

local f_comment = Field.new("frame.comment")

function pcapy.dissector(tvb, pinfo, tree)
    for _, info in ipairs({ f_comment() }) do
        local text = tostring(info.value)
        local app = text:match("^app=(%S+)")
        if app then
            local uid = tonumber(text:match("uid=(%d+)"))
            local t = tree:add(pcapy, tvb(0, 0), "Pcapy")
            t:add(f_app, tvb(0, 0), app)
            if uid then t:add(f_uid, tvb(0, 0), uid) end
            return
        end
    end
end

register_postdissector(pcapy)
